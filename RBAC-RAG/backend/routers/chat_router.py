"""Chat router: conversations + messages + RAG ask.

The RBAC path enforces role filtering INSIDE the SQL query. This module keeps
the top-level `ask` endpoint small by delegating to focused helpers.
"""
import json
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from deps import get_db, require_approved
from schemas import ConversationOut, MessageOut, AskRequest, AskResponse
from utils import fmt_vec
import nim_client
from retrieval import (
    hybrid_retrieve, assert_rbac, RetrievedChunk,
    DENSE_K, LEXICAL_K, FUSE_K, RRF_K,
    is_inventory_question, list_documents, format_document_inventory,
    is_document_summary_question, document_reference,
    resolve_document, resolve_document_by_id, document_chunks,
)
from reranker import rerank, RERANK_TOP_N
from document_summarizer import summarize_document

router = APIRouter(prefix="/chat", tags=["chat"])
logger = logging.getLogger(__name__)

TOP_K = 5


# ---------- Conversations ----------

@router.get("/conversations", response_model=list[ConversationOut])
async def list_conversations(user: dict = Depends(require_approved), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        text(
            "SELECT id, title, created_at, updated_at FROM conversations "
            "WHERE user_id = CAST(:u AS uuid) ORDER BY updated_at DESC LIMIT 100"
        ),
        {"u": user["id"]},
    )
    return [
        ConversationOut(id=str(r.id), title=r.title, created_at=r.created_at, updated_at=r.updated_at)
        for r in result.fetchall()
    ]


@router.get("/conversations/{conv_id}/messages", response_model=list[MessageOut])
async def list_messages(conv_id: str, user: dict = Depends(require_approved), db: AsyncSession = Depends(get_db)):
    own = await db.execute(
        text("SELECT id FROM conversations WHERE id = CAST(:c AS uuid) AND user_id = CAST(:u AS uuid)"),
        {"c": conv_id, "u": user["id"]},
    )
    if not own.first():
        raise HTTPException(status_code=404, detail="Conversation not found")

    result = await db.execute(
        text(
            "SELECT id, role, content, citations, retrieved_count, blocked_count, retrieval_detail, created_at "
            "FROM messages WHERE conversation_id = CAST(:c AS uuid) ORDER BY created_at ASC"
        ),
        {"c": conv_id},
    )
    return [
        MessageOut(
            id=str(r.id), role=r.role, content=r.content,
            citations=r.citations, retrieved_count=r.retrieved_count,
            blocked_count=r.blocked_count, retrieval_detail=r.retrieval_detail,
            created_at=r.created_at,
        )
        for r in result.fetchall()
    ]


@router.delete("/conversations/{conv_id}")
async def delete_conversation(conv_id: str, user: dict = Depends(require_approved), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        text("DELETE FROM conversations WHERE id = CAST(:c AS uuid) AND user_id = CAST(:u AS uuid) RETURNING id"),
        {"c": conv_id, "u": user["id"]},
    )
    if not result.first():
        raise HTTPException(status_code=404, detail="Conversation not found")
    await db.commit()
    return {"deleted": True}


# ---------- Ask helpers ----------


async def _ensure_conversation(db: AsyncSession, user_id: str, conv_id: str | None, question: str) -> str:
    """Verify ownership if a conv_id is supplied, or create a new conversation.
    Returns the conversation id as string.
    """
    if conv_id:
        own = await db.execute(
            text("SELECT id FROM conversations WHERE id = CAST(:c AS uuid) AND user_id = CAST(:u AS uuid)"),
            {"c": conv_id, "u": user_id},
        )
        if not own.first():
            raise HTTPException(status_code=404, detail="Conversation not found")
        return conv_id

    title = question.strip().split("\n")[0][:60] or "New conversation"
    ins = await db.execute(
        text("INSERT INTO conversations (user_id, title) VALUES (CAST(:u AS uuid), :t) RETURNING id"),
        {"u": user_id, "t": title},
    )
    return str(ins.first().id)


async def _insert_user_message(db: AsyncSession, conv_id: str, question: str):
    row = (await db.execute(
        text(
            "INSERT INTO messages (conversation_id, role, content) "
            "VALUES (CAST(:c AS uuid), 'user', :q) "
            "RETURNING id, role, content, citations, retrieved_count, blocked_count, retrieval_detail, created_at"
        ),
        {"c": conv_id, "q": question},
    )).first()
    await db.commit()
    return row


def _build_citations_and_details(rows: list[RetrievedChunk]):
    citations = []
    seen_titles = set()
    retrieved_details = []
    for c in rows:
        title = c.title
        if title not in seen_titles:
            seen_titles.add(title)
            citations.append({
                "document_id": c.document_id, "title": title, "source": c.source,
                "page": c.page, "chunk_id": c.id, "chunk_index": c.chunk_index,
            })
        detail = {
            "document_id": c.document_id,
            "title": title,
            "source": c.source,
            "page": c.page,
            "chunk_id": c.id,
            "chunk_index": c.chunk_index,
            "allowed_roles": list(c.allowed_roles or []),
        }
        if c.distance is not None:
            detail["distance"] = c.distance
        if c.dense_rank is not None:
            detail["dense_rank"] = c.dense_rank
        if c.lexical_rank is not None:
            detail["lexical_rank"] = c.lexical_rank
        detail["rrf_score"] = c.rrf_score
        if c.rerank_score is not None:
            detail["rerank_score"] = c.rerank_score
        if c.rerank_rank is not None:
            detail["rerank_rank"] = c.rerank_rank
        retrieved_details.append(detail)
    return citations, retrieved_details


async def _generate_answer(rows: list[RetrievedChunk], question: str, admin_bypass: bool) -> str:
    if not rows:
        return (
            "I don't have any documents in the knowledge base yet."
            if admin_bypass
            else "I don't have documents that your role is allowed to see for this question."
        )
    context = "\n\n".join(
        f"[Source #{i + 1}: {c.source}; page {c.page or 'unknown'}; chunk {c.id}]\n{c.content}"
        for i, c in enumerate(rows)
    )
    system_prompt = (
        "You are SENTRY/RAG, a permission-aware assistant. Answer the user's question "
        "using ONLY the sources provided below. Cite sources as (Source: filename, page N, chunk ID) "
        "when page metadata is available, otherwise use (Source: filename, chunk ID). "
        "If the sources don't contain the answer, respond exactly: "
        "'I don't have documents that answer this question.' Do not use general knowledge. "
        "Do not make up sources. "
        "\n\nDEFENSE-IN-DEPTH SOURCE RULES — follow strictly: "
        "\n- The ONLY valid document/source identities are the filenames given explicitly in the "
        "[Source #N: filename; ...] headers above. A document is 'in the knowledge base' only if "
        "its own header appears in this context — never name documents or report titles that happen "
        "to appear as TEXT inside a source's content; those are merely content the source discusses. "
        "\n- Do NOT list, enumerate, or summarize documents by names found only within chunk text "
        "(e.g. references/further-reading sections). Those are not retrieved sources. "
        "\n- When asked what documents are in the knowledge base, list ONLY the filenames from the "
        "provided [Source #N: ...] headers — never text extracted from within the chunks."
    )
    user_prompt = f"Question: {question}\n\nSources:\n{context}"
    return await nim_client.chat(system_prompt, user_prompt, max_tokens=700, temperature=0.2)


async def _persist_assistant_message(
    db: AsyncSession,
    conv_id: str,
    answer: str,
    citations: list[dict],
    retrieved_count: int,
    blocked_count: int,
    retrieval_detail: dict,
):
    row = (await db.execute(
        text(
            "INSERT INTO messages (conversation_id, role, content, citations, retrieved_count, blocked_count, retrieval_detail) "
            "VALUES (CAST(:c AS uuid), 'assistant', :m, CAST(:cit AS jsonb), :rc, :bc, CAST(:rd AS jsonb)) "
            "RETURNING id, role, content, citations, retrieved_count, blocked_count, retrieval_detail, created_at"
        ),
        {
            "c": conv_id, "m": answer, "cit": json.dumps(citations),
            "rc": retrieved_count, "bc": blocked_count,
            "rd": json.dumps(retrieval_detail),
        },
    )).first()
    await db.execute(
        text("UPDATE conversations SET updated_at = now() WHERE id = CAST(:c AS uuid)"),
        {"c": conv_id},
    )
    await db.commit()
    return row


# ---------- Document-summary handler ----------


# Cap for chunk detail records echoed back to the UI in document_summary mode.
# The full chunk list may be large; we bound what the frontend receives while
# keeping real filename/page/chunk metadata for the first few chunks.
SUMMARY_DETAIL_CAP = 5

_NO_MATCH_MSG = "I don't have access to a document matching that request. Please name a document you have access to and I'll summarize it."


async def _summary_details(rows: list[RetrievedChunk], cap: int = SUMMARY_DETAIL_CAP) -> list[dict]:
    """Bounded retrieval-detail rows for document_summary mode (document order)."""
    details: list[dict] = []
    for c in rows[:cap]:
        details.append({
            "document_id": c.document_id,
            "title": c.title,
            "source": c.source,
            "page": c.page,
            "chunk_id": c.id,
            "chunk_index": c.chunk_index,
            "allowed_roles": list(c.allowed_roles or []),
        })
    return details


async def _context_document_id(db: AsyncSession, conv_id: str) -> str | None:
    """Distinct document ids referenced by this conversation's citations.

    Returns the single id if exactly ONE distinct document was referenced;
    ``__ambiguous__`` if more than one; ``None`` if none. Caller re-checks
    current authorization before using the id.
    """
    result = await db.execute(
        text(
            "SELECT citations, retrieval_detail FROM messages "
            "WHERE conversation_id = CAST(:c AS uuid) AND role = 'assistant' "
            "ORDER BY created_at DESC LIMIT 30"
        ),
        {"c": conv_id},
    )
    ids: list[str] = []
    seen: set[str] = set()
    for r in result.fetchall():
        for cit in (r.citations or []):
            did = cit.get("document_id")
            if did and did not in seen:
                seen.add(did)
                ids.append(str(did))
        for item in ((r.retrieval_detail or {}).get("retrieved") or []):
            did = item.get("document_id")
            if did and did not in seen:
                seen.add(did)
                ids.append(str(did))
    if not ids:
        return None
    if len(ids) > 1:
        return "__ambiguous__"
    return ids[0]


def _clarify_message(reason: str, candidates: list[dict] | None = None) -> str:
    if reason == "no_match":
        return _NO_MATCH_MSG
    if reason == "ambiguous" and candidates:
        names = ", ".join(f"{d['title']} ({d['filename']})" for d in candidates)
        return (
            f"Multiple documents match that reference. Which one would you like "
            f"summarized? Available matches: {names}"
        )
    if reason == "no_chunks":
        return "I don't have content in that document that your role is allowed to see."
    # no_context / ambiguous_context / unauthorized_deleted — stay vague.
    return (
        "I can summarize a document you have access to - tell me which one and "
        "I'll summarize it for you."
    )


async def _handle_document_summary(
    db: AsyncSession,
    conv_id: str,
    user_row,
    question: str,
    role: str,
    admin_bypass: bool,
) -> AskResponse:
    """Document-scoped summary path: resolve -> RBAC re-check -> chunks -> summarize.

    Never falls back to global RAG on resolution/authorization failure: it
    returns a safe clarification/no-match response instead, so an inaccessible
    document is indistinguishable from a nonexistent one.
    """
    ref = document_reference(question)
    matched: list[dict] = []
    doc: dict | None = None
    reason: str | None = None
    candidates: list[dict] = []

    if ref["kind"] in ("filename", "numeric"):
        matched = await resolve_document(db, ref, role, admin_bypass)
        if len(matched) == 1:
            doc = matched[0]
        elif len(matched) > 1:
            reason = "ambiguous"
            candidates = matched
        else:
            reason = "no_match"
    else:
        # generic ("the report" / "this pdf" / "it") -> conversation context.
        ctx = await _context_document_id(db, conv_id)
        if ctx is None:
            reason = "no_context"
        elif ctx == "__ambiguous__":
            reason = "ambiguous_context"
        else:
            doc = await resolve_document_by_id(db, ctx, role, admin_bypass)
            if doc is None:
                reason = "unauthorized_deleted"

    pipeline = {
        "mode": "document_summary",
        "dense_k": DENSE_K, "lexical_k": LEXICAL_K,
        "fuse_k": FUSE_K, "rrf_k": RRF_K, "rerank_top_n": RERANK_TOP_N,
    }

    if reason is not None:
        answer = _clarify_message(reason, candidates)
        retrieval_detail = {
            "retrieved": [],
            "blocked": [],
            "role": role,
            "admin_bypass": admin_bypass,
            "top_k": TOP_K,
            "pipeline": {**pipeline, "reason": reason, "resolved_document": None},
        }
        asst_row = await _persist_assistant_message(db, conv_id, answer, [], 0, 0, retrieval_detail)
        return AskResponse(
            conversation_id=conv_id,
            user_message=MessageOut(
                id=str(user_row.id), role="user", content=user_row.content,
                citations=None, retrieved_count=None, blocked_count=None,
                retrieval_detail=None, created_at=user_row.created_at,
            ),
            assistant_message=MessageOut(
                id=str(asst_row.id), role="assistant", content=asst_row.content,
                citations=asst_row.citations, retrieved_count=asst_row.retrieved_count,
                blocked_count=asst_row.blocked_count, retrieval_detail=asst_row.retrieval_detail,
                created_at=asst_row.created_at,
            ),
        )

    # Authorized document resolved -> fetch ONLY its chunks with RBAC inside SQL.
    chunks = await document_chunks(db, doc["id"], role, admin_bypass)
    if not chunks:
        answer = _clarify_message("no_chunks")
        retrieval_detail = {
            "retrieved": [],
            "blocked": [],
            "role": role,
            "admin_bypass": admin_bypass,
            "top_k": TOP_K,
            "pipeline": {
                **pipeline,
                "reason": "no_chunks",
                "resolved_document": {"id": doc["id"], "title": doc["title"], "filename": doc["filename"]},
            },
        }
        asst_row = await _persist_assistant_message(db, conv_id, answer, [], 0, 0, retrieval_detail)
        return AskResponse(
            conversation_id=conv_id,
            user_message=MessageOut(
                id=str(user_row.id), role="user", content=user_row.content,
                citations=None, retrieved_count=None, blocked_count=None,
                retrieval_detail=None, created_at=user_row.created_at,
            ),
            assistant_message=MessageOut(
                id=str(asst_row.id), role="assistant", content=asst_row.content,
                citations=asst_row.citations, retrieved_count=asst_row.retrieved_count,
                blocked_count=asst_row.blocked_count, retrieval_detail=asst_row.retrieval_detail,
                created_at=asst_row.created_at,
            ),
        )

    # Defense-in-depth: chunk-level RBAC re-check (should never fire — SQL filtered).
    assert_rbac(chunks, role, admin_bypass)

    summary, chunk_count, llm_calls = await summarize_document(chunks, doc, admin_bypass)

    citations = [{
        "document_id": doc["id"],
        "title": doc["title"],
        "source": doc["filename"],
        "page": None,
        "chunk_id": None,
        "chunk_index": None,
    }]
    retrieval_detail = {
        "retrieved": await _summary_details(chunks),
        "blocked": [],
        "role": role,
        "admin_bypass": admin_bypass,
        "top_k": TOP_K,
        "pipeline": {
            **pipeline,
            "document_id": doc["id"],
            "title": doc["title"],
            "filename": doc["filename"],
            "chunk_count": chunk_count,
            "llm_calls": llm_calls,
            "reason": None,
        },
        "document_count": 1,
    }
    asst_row = await _persist_assistant_message(
        db, conv_id, summary, citations, chunk_count, 0, retrieval_detail,
    )
    return AskResponse(
        conversation_id=conv_id,
        user_message=MessageOut(
            id=str(user_row.id), role="user", content=user_row.content,
            citations=None, retrieved_count=None, blocked_count=None,
            retrieval_detail=None, created_at=user_row.created_at,
        ),
        assistant_message=MessageOut(
            id=str(asst_row.id), role="assistant", content=asst_row.content,
            citations=asst_row.citations, retrieved_count=asst_row.retrieved_count,
            blocked_count=asst_row.blocked_count, retrieval_detail=asst_row.retrieval_detail,
            created_at=asst_row.created_at,
        ),
    )


# ---------- Ask endpoint ----------


@router.post("/ask", response_model=AskResponse)
async def ask(req: AskRequest, user: dict = Depends(require_approved), db: AsyncSession = Depends(get_db)):
    role = user["role"]
    admin_bypass = (role == "admin")

    conv_id = await _ensure_conversation(db, user["id"], req.conversation_id, req.question)
    user_row = await _insert_user_message(db, conv_id, req.question)

    # Corpus-inventory questions ("what documents are in the knowledge base")
    # cannot be answered by RAG chunk retrieval — top-K similarity only returns
    # fragments of whatever chunk matches, never a true corpus inventory.
    # Route them to a direct, RBAC-filtered documents query instead — BEFORE any
    # embedding / retrieval / reranking, so inventory questions never hit NIM.
    if is_inventory_question(req.question):
        docs = await list_documents(db, role, admin_bypass)
        answer = format_document_inventory(docs, role)
        retrieval_detail = {
            "retrieved": [],
            "blocked": [],
            "role": role,
            "admin_bypass": admin_bypass,
            "top_k": TOP_K,
            "pipeline": {
                "mode": "corpus_inventory",
                "dense_k": DENSE_K, "lexical_k": LEXICAL_K,
                "fuse_k": FUSE_K, "rrf_k": RRF_K,
                "rerank_top_n": RERANK_TOP_N,
            },
            "document_count": len(docs),
        }
        asst_row = await _persist_assistant_message(
            db, conv_id, answer, [], 0, 0, retrieval_detail,
        )
        return AskResponse(
            conversation_id=conv_id,
            user_message=MessageOut(
                id=str(user_row.id), role="user", content=user_row.content,
                citations=None, retrieved_count=None, blocked_count=None,
                retrieval_detail=None, created_at=user_row.created_at,
            ),
            assistant_message=MessageOut(
                id=str(asst_row.id), role="assistant", content=asst_row.content,
                citations=asst_row.citations, retrieved_count=asst_row.retrieved_count,
                blocked_count=asst_row.blocked_count, retrieval_detail=asst_row.retrieval_detail,
                created_at=asst_row.created_at,
            ),
        )

    # Document-summary questions ("summarize the 067 pdf") cannot be answered by
    # global top-K RAG (which returns the K most relevant fragments, not broad
    # document coverage). Resolve the requested document strictly against
    # authorized metadata, then summarize ONLY that document's chunks.
    if is_document_summary_question(req.question):
        return await _handle_document_summary(db, conv_id, user_row, req.question, role, admin_bypass)

    # Embed the question
    q_emb = (await nim_client.embed([req.question], input_type="query"))[0]
    q_vec = fmt_vec(q_emb)

    # Hybrid retrieval: dense (pgvector) + BM25 lexical + RRF fusion, with RBAC
    # pre-filtered inside SQL on both legs (admin bypass skips that filter).
    fused, blocked = await hybrid_retrieve(db, q_vec, req.question, role, admin_bypass)

    # Defense-in-depth: never expected to fire (real enforcement is in SQL).
    assert_rbac(fused, role, admin_bypass)

    # Rerank the fused candidates down to the final TOP_K sent to the LLM.
    ranked = await rerank(fused, req.question)
    final_rows = ranked[:TOP_K]

    citations, retrieved_details = _build_citations_and_details(final_rows)
    retrieved_count = len(final_rows)
    blocked_count = len(blocked)

    # Generate answer
    answer = await _generate_answer(final_rows, req.question, admin_bypass)

    retrieval_detail = {
        "retrieved": retrieved_details,
        "blocked": blocked,
        "role": role,
        "admin_bypass": admin_bypass,
        "top_k": TOP_K,
        "pipeline": {
            "dense_k": DENSE_K, "lexical_k": LEXICAL_K,
            "fuse_k": FUSE_K, "rrf_k": RRF_K,
            "rerank_top_n": RERANK_TOP_N,
        },
    }

    asst_row = await _persist_assistant_message(
        db, conv_id, answer, citations, retrieved_count, blocked_count, retrieval_detail,
    )

    return AskResponse(
        conversation_id=conv_id,
        user_message=MessageOut(
            id=str(user_row.id), role="user", content=user_row.content,
            citations=None, retrieved_count=None, blocked_count=None,
            retrieval_detail=None, created_at=user_row.created_at,
        ),
        assistant_message=MessageOut(
            id=str(asst_row.id), role="assistant", content=asst_row.content,
            citations=asst_row.citations, retrieved_count=asst_row.retrieved_count,
            blocked_count=asst_row.blocked_count, retrieval_detail=asst_row.retrieval_detail,
            created_at=asst_row.created_at,
        ),
    )
