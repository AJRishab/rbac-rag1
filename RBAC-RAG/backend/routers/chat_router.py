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
)
from reranker import rerank, RERANK_TOP_N

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
        "Do not make up sources."
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


# ---------- Ask endpoint ----------


@router.post("/ask", response_model=AskResponse)
async def ask(req: AskRequest, user: dict = Depends(require_approved), db: AsyncSession = Depends(get_db)):
    role = user["role"]
    admin_bypass = (role == "admin")

    conv_id = await _ensure_conversation(db, user["id"], req.conversation_id, req.question)
    user_row = await _insert_user_message(db, conv_id, req.question)

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
