"""Hybrid retrieval: dense (pgvector) + BM25 lexical + RRF fusion.

Built from scratch on top of the pre-existing dense-only leg, which is factored
out here with its behavior unchanged (same SQL, same RBAC filter inside the
WHERE clause).

RBAC is enforced INSIDE the SQL query on BOTH legs (``WHERE d.status =
'published' AND c.allowed_roles && ARRAY[:role]``) so restricted chunks never
leave the database for an unauthorized caller. A post-fusion
:func:`assert_rbac` step adds defense-in-depth: it should never fire, and if it
does it means the pre-filter regressed and must be surfaced loudly.
"""
import logging
import re
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from rank_bm25 import BM25Okapi

logger = logging.getLogger(__name__)

# Candidate-pool sizes per leg. Larger than the final top-k so fusion + rerank
# have a real pool to work with before truncating to TOP_K in the LLM call.
DENSE_K = 20    # candidates pulled by the dense (pgvector) leg
LEXICAL_K = 20  # candidates returned by the BM25 lexical leg
FUSE_K = 20     # top-N fused candidates handed to the reranker
RRF_K = 60      # standard reciprocal-rank-fusion smoothing constant


@dataclass
class RetrievedChunk:
    """Row shape for a chunk travelling through the whole pipeline."""

    id: str                       # chunks.id (bigserial, str)
    document_id: str
    chunk_index: int
    content: str
    allowed_roles: list[str]
    title: str                    # documents.title (for citations)
    source: str                   # documents.filename
    page: int | None              # chunks.source_page
    # dense
    distance: float | None = None
    dense_rank: int | None = None
    # lexical (BM25)
    bm25_score: float | None = None
    lexical_rank: int | None = None
    # fused / reranked
    rrf_score: float = 0.0
    rerank_score: float | None = None
    rerank_rank: int | None = None


def _tokenize(text_: str) -> list[str]:
    """Small BM25 tokenizer: lowercase, split on runs of alphanumerics."""
    return re.findall(r"[a-z0-9]+", text_.lower())


def _chunk_from_dense_row(row, rank: int) -> RetrievedChunk:
    return RetrievedChunk(
        id=str(row.chunk_id),
        document_id=str(row.document_id),
        chunk_index=int(row.chunk_index),
        content=row.content,
        allowed_roles=list(row.allowed_roles or []),
        title=row.doc_title,
        source=row.source,
        page=row.source_page,
        distance=float(row.distance),
        dense_rank=rank,
    )


async def _dense_retrieve(
    db: AsyncSession,
    q_vec: str,
    role: str | None,
    admin_bypass: bool,
    k: int = DENSE_K,
) -> tuple[list[RetrievedChunk], list[dict]]:
    """RBAC pre-filtered dense retrieval (role check INSIDE SQL), or admin bypass.

    Returns ``(chunks, blocked_details)``. For admin bypass the status/role
    filter is omitted exactly as the pre-existing ``_retrieve_admin`` did, and
    blocked is empty.
    """
    if admin_bypass:
        rows = (await db.execute(
            text(
                "SELECT c.id AS chunk_id, c.document_id, c.chunk_index, c.source_page, c.content, c.allowed_roles, "
                "d.title AS doc_title, d.filename AS source, (c.embedding <=> CAST(:q AS vector)) AS distance "
                "FROM chunks c JOIN documents d ON d.id = c.document_id "
                "ORDER BY c.embedding <=> CAST(:q AS vector) LIMIT :k"
            ),
            {"q": q_vec, "k": k},
        )).fetchall()
        return [_chunk_from_dense_row(r, i + 1) for i, r in enumerate(rows)], []

    rows = (await db.execute(
        text(
            "SELECT c.id AS chunk_id, c.document_id, c.chunk_index, c.source_page, c.content, c.allowed_roles, "
            "d.title AS doc_title, d.filename AS source, (c.embedding <=> CAST(:q AS vector)) AS distance "
            "FROM chunks c JOIN documents d ON d.id = c.document_id "
            "WHERE d.status = 'published' AND c.allowed_roles && :r "
            "ORDER BY c.embedding <=> CAST(:q AS vector) LIMIT :k"
        ),
        {"q": q_vec, "r": [role], "k": k},
    )).fetchall()

    # Unfiltered measurement for the transparency/blocked list (same approach as
    # the pre-existing _retrieve_role_filtered): what the role could NOT see.
    unfiltered = (await db.execute(
        text(
            "SELECT c.id AS chunk_id, c.document_id, c.chunk_index, c.source_page, c.allowed_roles, "
            "d.title AS doc_title, d.filename AS source "
            "FROM chunks c JOIN documents d ON d.id = c.document_id "
            "WHERE d.status = 'published' "
            "ORDER BY c.embedding <=> CAST(:q AS vector) LIMIT :k"
        ),
        {"q": q_vec, "k": k},
    )).fetchall()

    kept_ids = {r.chunk_id for r in rows}
    blocked = [
        {
            "document_id": str(r.document_id),
            "title": r.doc_title,
            "source": r.source,
            "page": r.source_page,
            "chunk_id": r.chunk_id,
            "chunk_index": r.chunk_index,
            "allowed_roles": list(r.allowed_roles or []),
            "reason": "role_mismatch",
        }
        for r in unfiltered
        if r.chunk_id not in kept_ids
    ]
    return [_chunk_from_dense_row(r, i + 1) for i, r in enumerate(rows)], blocked
async def _lexical_retrieve(
    db: AsyncSession,
    query_text: str,
    role: str | None,
    admin_bypass: bool,
    k: int = LEXICAL_K,
) -> list[RetrievedChunk]:
    """In-process, real BM25 over the RBAC pre-filtered candidate pool.

    Queries only published chunks the caller's role may see (admins bypass the
    filter, mirroring the dense leg). The candidate pool is fetched from
    Postgres and scored with rank_bm25 — restricted chunks never leave the DB.
    """
    tokens = _tokenize(query_text)
    if not tokens:
        return []

    if admin_bypass:
        rows = (await db.execute(
            text(
                "SELECT c.id AS chunk_id, c.document_id, c.chunk_index, c.source_page, c.content, c.allowed_roles, "
                "d.title AS doc_title, d.filename AS source "
                "FROM chunks c JOIN documents d ON d.id = c.document_id "
                "ORDER BY c.id"
            ),
        )).fetchall()
    else:
        rows = (await db.execute(
            text(
                "SELECT c.id AS chunk_id, c.document_id, c.chunk_index, c.source_page, c.content, c.allowed_roles, "
                "d.title AS doc_title, d.filename AS source "
                "FROM chunks c JOIN documents d ON d.id = c.document_id "
                "WHERE d.status = 'published' AND c.allowed_roles && :r "
                "ORDER BY c.id"
            ),
            {"r": [role]},
        )).fetchall()

    if not rows:
        return []

    corpus = [_tokenize(r.content) for r in rows]
    bm25 = BM25Okapi(corpus)
    scores = bm25.get_scores(tokens)

    # Only genuine lexical hits (score > 0) enter the candidate pool; arbitrary
    # zero-score rows would only dilute fusion with non-matches.
    matched = [i for i, s in enumerate(scores) if s > 0]
    matched.sort(key=lambda i: (-scores[i], rows[i].chunk_id))  # score desc, id tiebreak
    ranked = matched[:k]
    chunks: list[RetrievedChunk] = []
    for rank, idx in enumerate(ranked, start=1):
        r = rows[idx]
        chunks.append(RetrievedChunk(
            id=str(r.chunk_id),
            document_id=str(r.document_id),
            chunk_index=int(r.chunk_index),
            content=r.content,
            allowed_roles=list(r.allowed_roles or []),
            title=r.doc_title,
            source=r.source,
            page=r.source_page,
            bm25_score=float(scores[idx]),
            lexical_rank=rank,
        ))
    return chunks


def _rrf_fuse(
    dense: list[RetrievedChunk],
    lexical: list[RetrievedChunk],
    k: int = RRF_K,
    fuse_k: int = FUSE_K,
) -> list[RetrievedChunk]:
    """Reciprocal-rank fusion combining the dense and lexical candidate sets.

    A chunk present in both legs keeps the dense row's metadata (distance,
    dense_rank) with the lexical fields overlaid (bm25_score, lexical_rank).
    """
    score: dict[str, float] = {}
    merged: dict[str, RetrievedChunk] = {}

    for rank, c in enumerate(dense, start=1):
        score[c.id] = score.get(c.id, 0.0) + 1.0 / (k + rank)
        merged[c.id] = c

    for rank, c in enumerate(lexical, start=1):
        score[c.id] = score.get(c.id, 0.0) + 1.0 / (k + rank)
        if c.id in merged:
            merged[c.id].bm25_score = c.bm25_score
            merged[c.id].lexical_rank = c.lexical_rank
        else:
            merged[c.id] = c

    for c in merged.values():
        c.rrf_score = score.get(c.id, 0.0)

    return sorted(
        merged.values(),
        key=lambda c: (-c.rrf_score, c.dense_rank if c.dense_rank is not None else fuse_k + 1),
    )[:fuse_k]


def assert_rbac(chunks: list[RetrievedChunk], role: str | None, admin_bypass: bool = False) -> None:
    """Defense-in-depth check — never expected to fire.

    The real enforcement already happened inside SQL (``allowed_roles &&
    ARRAY[:role]``). If a fused chunk reaches app memory that the caller cannot
    read, the pre-filter regressed and we must surface it loudly rather than
    silently continue.
    """
    if admin_bypass:
        return
    bad = [c.id for c in chunks if role not in (c.allowed_roles or [])]
    if bad:
        logger.error(
            "RBAC defense-in-depth check FAILED: %d unauthorized chunk(s) reached fusion (%s), role=%s",
            len(bad), bad, role,
        )
        raise RuntimeError(
            f"RBAC defense-in-depth check failed: {len(bad)} chunk(s) not authorized for role "
            f"'{role}': {bad}"
        )


async def hybrid_retrieve(
    db: AsyncSession,
    q_vec: str,
    query_text: str,
    role: str | None,
    admin_bypass: bool = False,
) -> tuple[list[RetrievedChunk], list[dict]]:
    """Dense + BM25 lexical + RRF fusion, RBAC-filtered in SQL on both legs.

    Returns ``(fused_chunks, blocked_details)``. The fused list (top ``FUSE_K``)
    is in RRF order and is the input to the reranker. ``blocked_details`` is
    only meaningful for non-admin callers (dense-leg unfiltered measurement).
    """
    dense, blocked = await _dense_retrieve(db, q_vec, role, admin_bypass)
    lexical = await _lexical_retrieve(db, query_text, role, admin_bypass)
    fused = _rrf_fuse(dense, lexical)
    return fused, blocked