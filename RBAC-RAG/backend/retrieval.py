"""Hybrid retrieval: dense (pgvector) + BM25 lexical + RRF fusion.

Built from scratch on top of the pre-existing dense-only leg, which is factored
out here with its behavior unchanged (same SQL, same RBAC filter inside the
WHERE clause).

RBAC is enforced INSIDE the SQL query on BOTH legs (``WHERE d.status =
'published' AND c.tenant_id = CAST(:tenant AS uuid) AND c.acl_principals &&
:principals``) so restricted chunks never leave the database for an
unauthorized caller — neither for role/principal reasons nor because they
belong to another tenant. A post-fusion :func:`assert_rbac` step adds
defense-in-depth (principals AND tenant): it should never fire, and if it does
it means the pre-filter regressed and must be surfaced loudly.

ADMIN BYPASS IS TENANT-SCOPED (behavior change from "admin sees everything"):
an admin skips the ``acl_principals`` check but every query still carries
``tenant_id = :tenant``. An admin from tenant A never sees tenant B's rows.
"""
import logging
import re
from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from rank_bm25 import BM25Okapi

logger = logging.getLogger(__name__)

# Tenant all pre-migration rows live in (see migrations/003_tenant_acl_audit.sql).
# A caller that somehow arrives without a tenant falls back to THIS tenant —
# never to "no tenant filter" (fail-closed).
DEFAULT_TENANT_ID = "00000000-0000-0000-0000-000000000001"


def principal_list(role: str | None) -> list[str]:
    """Caller's ACL principals for ``acl_principals && :principals`` checks.

    Today a principal is just the caller's role. When groups arrive later this
    is the single place to extend (e.g. append ``group:<id>`` entries) — no
    schema or query changes needed anywhere else.
    """
    return [f"role:{role}"] if role else []

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
    # tenant / ACL (migrations/003): carried so assert_rbac can verify tenant
    # match and the UI/audit paths can see the version that was served.
    tenant_id: str | None = None
    acl_principals: list[str] = field(default_factory=list)
    acl_version: int | None = None


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
        tenant_id=str(row.tenant_id) if row.tenant_id else None,
        acl_principals=list(row.acl_principals or []),
        acl_version=row.acl_version,
    )


async def _dense_retrieve(
    db: AsyncSession,
    q_vec: str,
    role: str | None,
    admin_bypass: bool,
    tenant: str | None = None,
    k: int = DENSE_K,
) -> tuple[list[RetrievedChunk], list[dict]]:
    """RBAC pre-filtered dense retrieval (ACL + tenant check INSIDE SQL), or
    tenant-scoped admin bypass.

    Returns ``(chunks, blocked_details)``. Admin bypass skips the
    ``acl_principals`` check but ALWAYS keeps ``tenant_id = :tenant`` — an
    admin from tenant A must never see tenant B's documents.
    """
    tenant_uuid = tenant or DEFAULT_TENANT_ID

    if admin_bypass:
        # Tenant-scoped bypass: principals check skipped, tenant check kept.
        rows = (await db.execute(
            text(
                "SELECT c.id AS chunk_id, c.document_id, c.chunk_index, c.source_page, c.content, c.allowed_roles, "
                "c.acl_principals, c.acl_version, c.tenant_id, "
                "d.title AS doc_title, d.filename AS source, (c.embedding <=> CAST(:q AS vector)) AS distance "
                "FROM chunks c JOIN documents d ON d.id = c.document_id "
                "WHERE c.tenant_id = CAST(:tenant AS uuid) "
                "ORDER BY c.embedding <=> CAST(:q AS vector) LIMIT :k"
            ),
            {"q": q_vec, "k": k, "tenant": tenant_uuid},
        )).fetchall()
        return [_chunk_from_dense_row(r, i + 1) for i, r in enumerate(rows)], []

    rows = (await db.execute(
        text(
            "SELECT c.id AS chunk_id, c.document_id, c.chunk_index, c.source_page, c.content, c.allowed_roles, "
            "c.acl_principals, c.acl_version, c.tenant_id, "
            "d.title AS doc_title, d.filename AS source, (c.embedding <=> CAST(:q AS vector)) AS distance "
            "FROM chunks c JOIN documents d ON d.id = c.document_id "
            "WHERE d.status = 'published' AND c.tenant_id = CAST(:tenant AS uuid) "
            "AND c.acl_principals && :principals "
            "ORDER BY c.embedding <=> CAST(:q AS vector) LIMIT :k"
        ),
        {"q": q_vec, "principals": principal_list(role), "tenant": tenant_uuid, "k": k},
    )).fetchall()

    # Unfiltered measurement for the transparency/blocked list (same approach as
    # the pre-existing _retrieve_role_filtered): what the role could NOT see.
    # TENANT-SCOPED on purpose: cross-tenant rows must not even leak their
    # title/filename metadata into the blocked list.
    unfiltered = (await db.execute(
        text(
            "SELECT c.id AS chunk_id, c.document_id, c.chunk_index, c.source_page, c.allowed_roles, "
            "d.title AS doc_title, d.filename AS source "
            "FROM chunks c JOIN documents d ON d.id = c.document_id "
            "WHERE d.status = 'published' AND c.tenant_id = CAST(:tenant AS uuid) "
            "ORDER BY c.embedding <=> CAST(:q AS vector) LIMIT :k"
        ),
        {"q": q_vec, "k": k, "tenant": tenant_uuid},
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
    tenant: str | None = None,
    k: int = LEXICAL_K,
) -> list[RetrievedChunk]:
    """In-process, real BM25 over the ACL+tenant pre-filtered candidate pool.

    Queries only published chunks the caller's principals may see in the
    caller's tenant (admins bypass the principals filter but stay tenant-scoped,
    mirroring the dense leg). The candidate pool is fetched from Postgres and
    scored with rank_bm25 — restricted chunks never leave the DB.
    """
    tokens = _tokenize(query_text)
    if not tokens:
        return []

    tenant_uuid = tenant or DEFAULT_TENANT_ID

    if admin_bypass:
        rows = (await db.execute(
            text(
                "SELECT c.id AS chunk_id, c.document_id, c.chunk_index, c.source_page, c.content, c.allowed_roles, "
                "c.acl_principals, c.acl_version, c.tenant_id, "
                "d.title AS doc_title, d.filename AS source "
                "FROM chunks c JOIN documents d ON d.id = c.document_id "
                "WHERE c.tenant_id = CAST(:tenant AS uuid) "
                "ORDER BY c.id"
            ),
            {"tenant": tenant_uuid},
        )).fetchall()
    else:
        rows = (await db.execute(
            text(
                "SELECT c.id AS chunk_id, c.document_id, c.chunk_index, c.source_page, c.content, c.allowed_roles, "
                "c.acl_principals, c.acl_version, c.tenant_id, "
                "d.title AS doc_title, d.filename AS source "
                "FROM chunks c JOIN documents d ON d.id = c.document_id "
                "WHERE d.status = 'published' AND c.tenant_id = CAST(:tenant AS uuid) "
                "AND c.acl_principals && :principals "
                "ORDER BY c.id"
            ),
            {"principals": principal_list(role), "tenant": tenant_uuid},
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
            tenant_id=str(r.tenant_id) if r.tenant_id else None,
            acl_principals=list(r.acl_principals or []),
            acl_version=r.acl_version,
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



_DOC_NOUN = r"document|documents|file|files|item|items|source|sources|paper|papers|report|reports|publication|publications|title|titles"
_DOC_KB = r"knowledge\s*base|\bkb\b|corpus|system|the\s+library|the\s+collection|database|rag|the\s+project|the\s+application|app|index|archive"

_DOC_NOUN_RE = re.compile(_DOC_NOUN, re.IGNORECASE)
_DOC_KB_RE = re.compile(_DOC_KB, re.IGNORECASE)


def is_inventory_question(text: str) -> bool:
    """True if `text` is a corpus-inventory question ("what documents are in
    the knowledge base?", "list the files in this system", "KB documents", ...).

    Routed to the direct `documents` query path instead of RAG chunk retrieval,
    because top-K similarity search over chunks can never produce a true
    corpus inventory — it can only return fragments of the matching chunk(s).

    Detection is a **two-independent-set AND**: the query must contain
    (1) a document-type noun AND (2) an explicit corpus-level anchor
    ("knowledge base" / "kb" / "the system" / ...). Both must be present, in
    any order, with no inventory verb required (so noun-only phrasings like
    "KB documents available" still classify).

    This avoids the two failure modes of RAG on such questions:
      * false positives on content questions that merely use "documents"
        (e.g. "how many documents mention the Mendoza Review" — has the noun
        but no anchor, so it correctly stays on the RAG path);
      * false positives on conceptual queries ("what is in the knowledge base")
        — has the anchor but no document noun, so stays on the RAG path.
    """
    t = (text or "").strip()
    if not t:
        return False
    if not _DOC_NOUN_RE.search(t):
        return False
    if not _DOC_KB_RE.search(t):
        return False
    return True


async def list_documents(
    db: AsyncSession, role: str | None, admin_bypass: bool = False, tenant: str | None = None,
) -> list[dict]:
    """RBAC-filtered corpus inventory, queried directly from `documents`.

    Mirrors the ACL contract in :func:`_dense_retrieve` exactly:
    non-admin callers are restricted in SQL to ``status = 'published'`` AND
    ``acl_principals && :principals``; admin bypass drops the principals filter
    but ALWAYS keeps ``tenant_id = :tenant`` (an admin never sees another
    tenant's documents), regardless of status/role otherwise.

    Returns dicts with title (falling back to filename when title is empty),
    filename, status, allowed_roles — the fields needed to answer inventory
    questions without ever touching chunks or the LLM.
    """
    tenant_uuid = tenant or DEFAULT_TENANT_ID
    if admin_bypass:
        sql = (
            "SELECT id, title, filename, status, allowed_roles "
            "FROM documents "
            "WHERE tenant_id = CAST(:tenant AS uuid) "
            "ORDER BY title NULLS LAST, filename"
        )
        result = await db.execute(text(sql), {"tenant": tenant_uuid})
    else:
        sql = (
            "SELECT id, title, filename, status, allowed_roles "
            "FROM documents "
            "WHERE status = 'published' "
            "  AND tenant_id = CAST(:tenant AS uuid) "
            "  AND acl_principals && :principals "
            "ORDER BY title NULLS LAST, filename"
        )
        result = await db.execute(text(sql), {"principals": principal_list(role), "tenant": tenant_uuid})
    rows = result.fetchall()
    out: list[dict] = []
    for r in rows:
        title = (r.title or "").strip() or r.filename
        out.append({
            "id": str(r.id),
            "title": title,
            "filename": r.filename,
            "status": r.status,
            "allowed_roles": list(r.allowed_roles or []),
        })
    return out


def format_document_inventory(docs: list[dict], role: str | None) -> str:
    """Format inventory rows into a grounded, RBAC-correct answer string."""
    if not docs:
        return "No documents are currently available to you in the knowledge base."
    lines = [f"- {d['title']}" for d in docs]
    header = "Documents available to you in the knowledge base:"
    return f"{header}\n" + "\n".join(lines)



# ==== Document-summary intent detection + safe document resolution ====
# A third scope alongside `corpus_inventory` and normal hybrid RAG: asking for
# a summary/overview of ONE named document. This cannot be answered by global
# top-K chunk similarity (which returns the K most relevant fragments, not
# broad document coverage), so it is resolved against `documents` metadata and
# then scoped to that single document's chunks - with RBAC enforced INSIDE each
# SQL query (never fetch-then-filter in Python).

_RE_SUMMARY_INTENT = re.compile(
    r"(?:"
    r"summari[sz]e|summari[sz]ing|summar[sy]|overview|\btl;?dr\b|\bgist\b|"
    r"key\s+points?|main\s+(?:points?|ideas?|takeaways?)|"
    r"what(?:'s|\s+is)\s+this\s+(?:document|report|pdf|file|paper|doc)(?:\s+about)?"
    r")",
    re.IGNORECASE,
)

_RE_REF_FILENAME = re.compile(
    r"\b([A-Za-z0-9][A-Za-z0-9._-]*\.(?:pdf|docx?|txt|md|markdown))\b",
    re.IGNORECASE,
)
_RE_REF_NUMERIC = re.compile(r"\b(\d{2,})\b")
_RE_REF_GENERIC = re.compile(
    r"\b(?:the|this|that)\s+(?:report|document|pdf|file|paper|doc)\b|\b(?:it|this)\b",
    re.IGNORECASE,
)
_EXT_RE = re.compile(r"\.(?:pdf|docx?|txt|md|markdown)$")

# Standard document-section names. Used for two things: extracting a requested
# section from a summary question ("summarize the abstract") and recognizing a
# section HEADING inside chunk text (document_summarizer.select_section_chunks).
# The list is generic paper/report structure - deliberately NOT tied to any
# specific document.
SECTION_WORDS: tuple[str, ...] = (
    "abstract", "executive summary", "introduction", "background",
    "related work", "literature review", "methodology", "methods",
    "materials and methods", "experimental setup", "experimental results",
    "evaluation", "results", "analysis", "discussion", "conclusions",
    "conclusion", "future work", "acknowledgements", "acknowledgments",
    "references", "appendix",
)
_RE_SECTION = re.compile(
    r"\b("
    + "|".join(re.escape(w) for w in sorted(SECTION_WORDS, key=len, reverse=True))
    + r")\b",
    re.IGNORECASE,
)


def document_section(text: str) -> str | None:
    """Extract a requested document-section name from a summary question.

    ``"Summarize the abstract of 1706.03762v7.pdf"`` -> ``"abstract"``.
    Returns ``None`` when no standard section is named, so ordinary
    whole-document summaries and normal RAG questions are unaffected.
    """
    m = _RE_SECTION.search(text or "")
    return m.group(1).lower() if m else None


def section_heading_line_re(section: str) -> re.Pattern[str]:
    """Standalone section-heading line matcher: 'Abstract', '1. Introduction',
    'II. RELATED WORK', 'References:'. Tolerates numbering prefixes, an
    optional trailing plural and punctuation. Mid-sentence mentions of the
    word do NOT match (the heading must end the line)."""
    esc = re.escape((section or "").strip()).replace(r"\ ", r"\s+")
    return re.compile(
        rf"^\s*(?:\d+(?:\.\d+)*[\.\)]?\s+|[ivxlc]+[\.\)]\s+)?{esc}s?\s*[:.\u2013\u2014-]?\s*$",
        re.IGNORECASE,
    )


def _slug(value: str) -> str:
    """Lowercase + collapse non-alphanumerics to single '-' separators."""
    return re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")


def _norm_filename(value: str) -> str:
    """Filename normalization for matching: lowercase, strip extension, slugify."""
    return _slug(_EXT_RE.sub("", (value or "").strip().lower()))


def _numeric_ids(value: str) -> set[int]:
    """Numeric 'identifier' tokens from a filename/title/ref, leading-zero aware.

    ``067`` and ``0067`` both normalize to ``{67}`` so the loose spoken form
    ``067 pdf`` can resolve the file ``0067-pdf.pdf``.
    """
    return {int(x) for x in re.findall(r"\d+", value or "")}


def is_document_summary_question(text: str) -> bool:
    """True if `text` asks to summarize / overview a *specific* document.

    Requires BOTH a summary intent (``summarize``, ``overview``, ``what is
    this document about``...) AND something to reference (a filename, a numeric
    id like ``067``, or a generic ``the report`` / ``this pdf`` / ``it``).

    This deliberately does NOT classify content questions that merely mention
    reports/documents: "What does the report say about X?" and "How many
    documents mention the Mendoza Review?" have no summary intent and stay on
    the normal RAG path.
    """
    t = (text or "").strip()
    if not t or not _RE_SUMMARY_INTENT.search(t):
        return False
    return bool(
        _RE_REF_FILENAME.search(t)
        or _RE_REF_NUMERIC.search(t)
        or _RE_REF_GENERIC.search(t)
        # A named section ("summarize the abstract") is also a document-scoped
        # summary request; the document resolves via conversation context like
        # the generic "the report" form.
        or document_section(t) is not None
    )


def document_reference(text: str) -> dict:
    """Extract the document reference from a summary query.

    Returns ``{"kind": "filename"|"numeric"|"generic", "value": str}``.
    - filename: an extension-qualified token (e.g. ``0067-pdf.pdf``)
    - numeric:  a numeric identifier (e.g. ``067`` in ``summarize the 067 pdf``)
    - generic:  ``the report`` / ``this document`` / ``it`` - only usable via
      conversation context
    """
    m = _RE_REF_FILENAME.search(text or "")
    if m:
        return {"kind": "filename", "value": m.group(1)}
    nums = _RE_REF_NUMERIC.findall(text or "")
    if nums:
        return {"kind": "numeric", "value": "-".join(nums)}
    if _RE_REF_GENERIC.search(text or ""):
        return {"kind": "generic", "value": ""}
    return {"kind": None, "value": ""}


async def _authorized_documents(
    db: AsyncSession,
    role: str | None,
    admin_bypass: bool,
    tenant: str | None = None,
    limit: int = 200,
) -> list[dict]:
    """All documents the caller may *see* - ACL boundary enforced in SQL.

    Non-admin: ``status='published' AND tenant_id = :tenant AND
    acl_principals && :principals``. Admin: bypasses the principals check but
    stays tenant-scoped (exactly like the dense leg). Unauthorized or
    cross-tenant documents never leave the database, so nothing about them
    (filename, title, existence, ambiguity hints) can leak into resolution
    results.
    """
    tenant_uuid = tenant or DEFAULT_TENANT_ID
    if admin_bypass:
        sql = (
            "SELECT id, title, filename, status, allowed_roles "
            "FROM documents WHERE tenant_id = CAST(:tenant AS uuid) ORDER BY filename LIMIT :lim"
        )
        rows = (await db.execute(text(sql), {"tenant": tenant_uuid, "lim": limit})).fetchall()
    else:
        sql = (
            "SELECT id, title, filename, status, allowed_roles "
            "FROM documents "
            "WHERE status = 'published' AND tenant_id = CAST(:tenant AS uuid) "
            "AND acl_principals && :principals "
            "ORDER BY filename LIMIT :lim"
        )
        rows = (await db.execute(
            text(sql), {"principals": principal_list(role), "tenant": tenant_uuid, "lim": limit},
        )).fetchall()
    return [
        {
            "id": str(r.id),
            "title": (r.title or "").strip() or r.filename,
            "filename": r.filename,
            "status": r.status,
            "allowed_roles": list(r.allowed_roles or []),
        }
        for r in rows
    ]


def _match_documents(docs: list[dict], ref: dict) -> list[dict]:
    """Deterministic tiered matching against an ALREADY-authorized doc list.

    Tiers (first tier with hits wins): 1) exact filename, 2) normalized
    filename, 3) exact title, 4) normalized title, 5) tightly-constrained
    numeric identifier match. Never broad substring matching; a non-unique
    match returns the full candidate list so the caller can ask for
    clarification instead of guessing.
    """
    value = (ref.get("value") or "").lower().strip()
    if not value:
        return []
    if ref.get("kind") not in ("filename", "numeric"):
        return []

    # 1 exact filename
    hits = [d for d in docs if (d["filename"] or "").lower().strip() == value]
    # 2 normalized filename
    if not hits:
        nv = _norm_filename(value)
        hits = [d for d in docs if _norm_filename(d["filename"]) == nv]
    # 3 exact title
    if not hits:
        hits = [d for d in docs if (d["title"] or "").strip().lower() == value]
    # 4 normalized title
    if not hits:
        nv = _slug(value)
        hits = [d for d in docs if _slug(d["title"]) == nv]
    # 5 tightly constrained numeric identifier
    if not hits:
        ref_nums = _numeric_ids(value)
        if ref_nums:
            hits = [
                d
                for d in docs
                if ref_nums <= (_numeric_ids(d["filename"]) | _numeric_ids(d["title"]))
            ]
    return hits


async def resolve_document(
    db: AsyncSession,
    ref: dict,
    role: str | None,
    admin_bypass: bool,
    tenant: str | None = None,
) -> list[dict]:
    """Resolve ``ref`` against authorized documents. Returns 0/1/N matches.

    Only documents the caller may access are ever queried (SQL filter, see
    :func:`_authorized_documents`), so an inaccessible — or cross-tenant —
    document cannot be distinguished from a nonexistent one.
    """
    docs = await _authorized_documents(db, role, admin_bypass, tenant=tenant)
    return _match_documents(docs, ref)


async def resolve_document_by_id(
    db: AsyncSession,
    document_id: str,
    role: str | None,
    admin_bypass: bool,
    tenant: str | None = None,
) -> dict | None:
    """Re-check current authorization for a known document id (contextual refs).

    Re-authorization happens in SQL so a document that became inaccessible,
    moved to another tenant, or was deleted after it appeared in conversation
    history resolves to ``None``.
    """
    tenant_uuid = tenant or DEFAULT_TENANT_ID
    if admin_bypass:
        # Tenant-scoped bypass: principals check skipped, tenant check kept.
        sql = (
            "SELECT id, title, filename, status, allowed_roles FROM documents "
            "WHERE id = CAST(:id AS uuid) AND tenant_id = CAST(:tenant AS uuid)"
        )
        row = (await db.execute(text(sql), {"id": document_id, "tenant": tenant_uuid})).first()
    else:
        sql = (
            "SELECT id, title, filename, status, allowed_roles FROM documents "
            "WHERE id = CAST(:id AS uuid) "
            "AND status = 'published' AND tenant_id = CAST(:tenant AS uuid) "
            "AND acl_principals && :principals"
        )
        row = (await db.execute(
            text(sql), {"id": document_id, "principals": principal_list(role), "tenant": tenant_uuid},
        )).first()
    if not row:
        return None
    return {
        "id": str(row.id),
        "title": (row.title or "").strip() or row.filename,
        "filename": row.filename,
        "status": row.status,
        "allowed_roles": list(row.allowed_roles or []),
    }


async def document_chunks(
    db: AsyncSession,
    document_id: str,
    role: str | None,
    admin_bypass: bool,
    tenant: str | None = None,
    limit: int | None = None,
) -> list[RetrievedChunk]:
    """ALL chunks of ONE resolved document, in document (chunk_index) order.

    RBAC is enforced INSIDE the SQL: the document must belong to the caller's
    tenant, and (non-admin) it must still be published AND the chunk's
    ``acl_principals`` must overlap the caller's principals. Admin bypass
    mirrors the dense leg: principals filter skipped, tenant filter KEPT.
    Never retrieve then filter in Python — restricted chunks for an
    unauthorized caller never leave the database.
    """
    tenant_uuid = tenant or DEFAULT_TENANT_ID
    base = (
        "SELECT c.id AS chunk_id, c.document_id, c.chunk_index, c.source_page, "
        "c.content, c.allowed_roles, c.acl_principals, c.acl_version, c.tenant_id, "
        "d.title AS doc_title, d.filename AS source "
        "FROM chunks c JOIN documents d ON d.id = c.document_id "
        "WHERE c.document_id = CAST(:id AS uuid) "
        "AND c.tenant_id = CAST(:tenant AS uuid) "
    )
    if admin_bypass:
        sql = base + "ORDER BY c.chunk_index"
        params: dict = {"id": document_id, "tenant": tenant_uuid}
    else:
        sql = base + (
            "AND d.status = 'published' AND c.acl_principals && :principals "
            "ORDER BY c.chunk_index"
        )
        params = {"id": document_id, "principals": principal_list(role), "tenant": tenant_uuid}
    if limit is not None:
        sql += f" LIMIT {int(limit)}"
    rows = (await db.execute(text(sql), params)).fetchall()
    return [
        RetrievedChunk(
            id=str(r.chunk_id),
            document_id=str(r.document_id),
            chunk_index=int(r.chunk_index),
            content=r.content,
            allowed_roles=list(r.allowed_roles or []),
            title=r.doc_title,
            source=r.source,
            page=r.source_page,
            tenant_id=str(r.tenant_id) if r.tenant_id else None,
            acl_principals=list(r.acl_principals or []),
            acl_version=r.acl_version,
        )
        for r in rows
    ]


def assert_rbac(
    chunks: list[RetrievedChunk],
    role: str | None,
    admin_bypass: bool = False,
    tenant: str | None = None,
) -> None:
    """Defense-in-depth check — never expected to fire.

    The real enforcement already happened inside SQL (``tenant_id = :tenant AND
    acl_principals && :principals``). If a fused chunk reaches app memory that
    the caller cannot read — for principal OR tenant reasons — the pre-filter
    regressed and we must surface it loudly rather than silently continue.

    Chunks that carry no ``tenant_id`` (legacy fixtures) cannot be tenant
    checked here; production rows always have one, so this is best-effort only
    and the SQL-level tenant filter remains the real boundary.
    """
    if admin_bypass:
        return
    bad_principals = [
        c.id for c in chunks
        if role not in (c.allowed_roles or [])
        and f"role:{role}" not in (c.acl_principals or [])
    ]
    bad_tenant = [
        c.id for c in chunks
        if tenant and c.tenant_id and c.tenant_id != tenant
    ]
    if bad_principals or bad_tenant:
        logger.error(
            "RBAC defense-in-depth check FAILED: %d unauthorized and %d cross-tenant "
            "chunk(s) reached fusion (principal_bad=%s, tenant_bad=%s), role=%s, tenant=%s",
            len(bad_principals), len(bad_tenant), bad_principals, bad_tenant, role, tenant,
        )
        raise RuntimeError(
            f"RBAC defense-in-depth check failed: "
            f"{len(bad_principals)} chunk(s) not authorized for principal 'role:{role}' "
            f"{bad_principals}; {len(bad_tenant)} chunk(s) from another tenant {bad_tenant}"
        )


async def hybrid_retrieve(
    db: AsyncSession,
    q_vec: str,
    query_text: str,
    role: str | None,
    admin_bypass: bool = False,
    tenant: str | None = None,
) -> tuple[list[RetrievedChunk], list[dict]]:
    """Dense + BM25 lexical + RRF fusion, ACL-filtered in SQL on both legs.

    Returns ``(fused_chunks, blocked_details)``. The fused list (top ``FUSE_K``)
    is in RRF order and is the input to the reranker. ``blocked_details`` is
    only meaningful for non-admin callers (dense-leg unfiltered measurement,
    tenant-scoped so cross-tenant metadata never leaks).
    """
    dense, blocked = await _dense_retrieve(db, q_vec, role, admin_bypass, tenant=tenant)
    lexical = await _lexical_retrieve(db, query_text, role, admin_bypass, tenant=tenant)
    fused = _rrf_fuse(dense, lexical)
    return fused, blocked