"""Tests for the document-summary scope (third pipeline path).

Covers detection, safe document resolution, RBAC enforcement (no unauthorized
leaks), document-scoped chunk retrieval, hierarchical summarization, citation
integrity, contextual references, and regressions for corpus-inventory and
normal RAG. Uses fake DB results and patched NIM calls - no live network.
"""
import asyncio
import json
import types
from datetime import datetime
from unittest.mock import patch

import pytest
from fastapi import HTTPException

import retrieval as R
import document_summarizer as S
from routers import admin_router as AR
from routers.chat_router import _handle_document_summary, _context_document_id
from schemas import UpdateDocRolesRequest, UpdateChunkRolesRequest, ApproveUserRequest


# Tenant fixtures: A is "ours", B is a foreign tenant no query may ever reach.
DEFAULT_TENANT = "00000000-0000-0000-0000-000000000001"
TENANT_A = "11111111-1111-1111-1111-111111111111"
TENANT_B = "22222222-2222-2222-2222-222222222222"


# ---------------- fakes ----------------


class FakeResult:
    def __init__(self, rows=None):
        self._rows = list(rows or [])

    def fetchall(self):
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None

    def scalar(self):
        return self._rows[0] if self._rows else None


class FakeDb:
    """Queued results + captured SQL statements/params for the async code paths."""

    def __init__(self, queue=None, statements=None):
        self._queue = list(queue or [])
        self.statements = statements if statements is not None else []
        self.params: list[dict | None] = []

    async def execute(self, stmt, params=None):
        self.statements.append(str(stmt))
        self.params.append(dict(params) if params else None)
        stmt_s = str(stmt)
        if "INSERT INTO messages" in stmt_s and params and params.get("rd") is not None:
            import json as _json
            row = asst_row(
                content=str(params.get("m") or ""),
                citations=_json.loads(params.get("cit") or "[]"),
                n=params.get("rc") or 0,
                rd=_json.loads(params.get("rd") or "{}"),
            )
            return FakeResult([row])
        return self._queue.pop(0) if self._queue else FakeResult()

    async def commit(self):
        return None

    async def rollback(self):
        return None


def docrow(did, title, filename, roles=None, status="published", tenant_id=DEFAULT_TENANT):
    return types.SimpleNamespace(
        id=did, title=title, filename=filename,
        allowed_roles=roles or [], status=status,
        tenant_id=tenant_id, chunk_count=0, uploaded_at=datetime(2026, 1, 1),
        uploaded_by="u1",
    )


def chunkrow(cid, did, idx, content, roles=None, page=None, acl_version=1, tenant_id=DEFAULT_TENANT):
    return types.SimpleNamespace(
        chunk_id=cid, document_id=did, chunk_index=idx, source_page=page,
        content=content, allowed_roles=roles or [],
        acl_principals=[f"role:{r}" for r in (roles or [])],
        acl_version=acl_version, tenant_id=tenant_id,
        doc_title="Doc T", source="source.pdf",
    )


def msgrow(citations, retrieval_detail=None):
    return types.SimpleNamespace(citations=citations, retrieval_detail=retrieval_detail or {})


def asst_row(content="ok", citations=None, n=1, rd=None):
    return types.SimpleNamespace(
        id="msg-1", role="assistant", content=content,
        citations=citations or [], retrieved_count=n, blocked_count=0,
        retrieval_detail=rd or {}, created_at="2026-01-01T00:00:00Z",
    )


def user_row():
    return types.SimpleNamespace(
        id="u1", role="user", content="q", created_at="2026-01-01T00:00:00Z",
    )


def run(coro):
    return asyncio.run(coro)


def _rk(i, roles=None, text=None, tenant=DEFAULT_TENANT):
    """RetrievedChunk helper."""
    return R.RetrievedChunk(
        id=str(i), document_id="d1", chunk_index=i,
        content=text or f"chunk number {i} with body text to pad the token count. " * 8,
        allowed_roles=roles or ["manager"],
        acl_principals=[f"role:{r}" for r in (roles or ["manager"])],
        tenant_id=tenant,
        title="Museums Matter, 2015",
        source="0067-pdf.pdf", page=i,
    )


def _doc_dict(did, title, filename, roles=None):
    return {"id": did, "title": title, "filename": filename,
            "status": "published", "allowed_roles": roles or []}


# ---------------- detection (tests 1, 15, 16) ----------------


@pytest.mark.parametrize("q", [
    "summarize the 067 pdf",
    "summarize 0067-pdf.pdf",
    "give me a summary of 0067",
    "give me an overview of the 0067 report",
    "what is this document about?",
    "what's this pdf about",
])
def test_1_document_summary_detection_positive(q):
    assert R.is_document_summary_question(q) is True


@pytest.mark.parametrize("q", [
    "What does the report say about X?",
    "How many documents mention the Mendoza Review?",
    "What documents are in the knowledge base?",
    "What is the Mendoza Review about?",
    "tell me about the Mendoza Review",
])
def test_1b_document_summary_detection_negative(q):
    assert R.is_document_summary_question(q) is False


def test_2_exact_filename_resolution():
    docs = [_doc_dict("a", "T", "0067-pdf.pdf")]
    hits = R._match_documents(docs, {"kind": "filename", "value": "0067-pdf.pdf"})
    assert len(hits) == 1


def test_3_normalized_filename_resolution():
    docs = [_doc_dict("a", "T", "0067-pdf.pdf")]
    assert [d["filename"] for d in R._match_documents(docs, {"kind": "numeric", "value": "0067"})] == ["0067-pdf.pdf"]
    assert [d["filename"] for d in R._match_documents(docs, {"kind": "numeric", "value": "067"})] == ["0067-pdf.pdf"]


def test_4_ambiguous_document_reference_returns_all():
    docs = [_doc_dict("a", "One", "0067-a.pdf"), _doc_dict("b", "Two", "0067-b.pdf")]
    hits = R._match_documents(docs, {"kind": "numeric", "value": "067"})
    assert len(hits) == 2  # not a silent guess


def test_5_no_match_returns_empty():
    docs = [_doc_dict("a", "T", "0001-a.pdf")]
    assert R._match_documents(docs, {"kind": "numeric", "value": "9999"}) == []


# ---------------- RBAC boundaries (tests 6-9 + security) ----------------


def test_6_authorized_document_resolution_sql_is_rbac_filtered():
    db = FakeDb()
    run(R._authorized_documents(db, role="manager", admin_bypass=False))
    sql = db.statements[0]
    assert "status = 'published'" in sql
    assert "acl_principals && :principals" in sql
    assert "tenant_id = CAST(:tenant AS uuid)" in sql


def test_6b_admin_resolution_bypasses_rbac():
    db = FakeDb()
    run(R._authorized_documents(db, role="admin", admin_bypass=True))
    sql = db.statements[0]
    assert "status = 'published'" not in sql
    assert "ARRAY[:role]" not in sql


def test_7_unauthorized_document_cannot_be_resolved():
    # The DB feed only contains authorized docs; resolution sees no trace of 0067.
    db = FakeDb([FakeResult([docrow("a", "Authorized", "0066.pdf", ["manager"])])])
    hits = run(R.resolve_document(db, {"kind": "numeric", "value": "067"}, "manager", False))
    assert hits == []


def test_8_unauthorized_document_chunks_cannot_be_retrieved():
    db = FakeDb()
    run(R.document_chunks(db, "doc-1", role="hr", admin_bypass=False))
    sql = db.statements[0]
    assert "d.status = 'published'" in sql
    assert "c.acl_principals && :principals" in sql
    assert "c.tenant_id = CAST(:tenant AS uuid)" in sql
    db2 = FakeDb()
    run(R.document_chunks(db2, "doc-1", role="admin", admin_bypass=True))
    sql2 = db2.statements[0]
    # Admin bypass skips the principals FILTER but NEVER the tenant check.
    assert "acl_principals &&" not in sql2
    assert "c.tenant_id = CAST(:tenant AS uuid)" in sql2
    assert "published" not in sql2


def test_9_chunk_level_rbac_still_applies():
    chunk = _rk(1)
    R.assert_rbac([chunk], role="manager", admin_bypass=False)  # ok
    with pytest.raises(RuntimeError):
        R.assert_rbac([chunk], role="hr", admin_bypass=False)   # unauthorized
    R.assert_rbac([chunk], role="hr", admin_bypass=True)        # admin bypass


def test_resolve_unique_and_by_id_reauthorization():
    db = FakeDb([FakeResult([docrow("d1", "0067-pdf.pdf", "0067-pdf.pdf", ["manager"])])])
    hits = run(R.resolve_document(db, {"kind": "numeric", "value": "067"}, "manager", False))
    assert [h["id"] for h in hits] == ["d1"]
    db2 = FakeDb()
    assert run(R.resolve_document_by_id(db2, "d1", role="hr", admin_bypass=False)) is None
    assert "acl_principals && :principals" in db2.statements[0]
    assert "tenant_id = CAST(:tenant AS uuid)" in db2.statements[0]


def test_security_similar_filename_no_leak():
    db = FakeDb([FakeResult([docrow("m", "Mine", "0066.pdf", ["manager"])])])
    hits = run(R.resolve_document(db, {"kind": "numeric", "value": "0067"}, "manager", False))
    assert hits == []


# ---------------- summarizer ----------------


def test_10_summary_uses_document_order():
    chunks = [_rk(i) for i in range(12)]
    groups = S._group_chunks(chunks, target_tokens=200)
    assert [c.chunk_index for g in groups for c in g] == list(range(12))
    assert len(groups) > 1


def test_11_small_document_single_batch():
    captured = []

    async def fake_chat(system, user, max_tokens=700, temperature=0.2):
        captured.append(system)
        assert "authorized document" in system
        assert "source" in system
        return "FINAL SUMMARY"

    with patch("document_summarizer.nim_client.chat", side_effect=fake_chat) as m:
        chunks = [_rk(i, text=f"short content {i}") for i in range(3)]
        summary, n, calls = run(S.summarize_document(
            chunks, {"id": "a", "title": "T", "filename": "0067-pdf.pdf"}, False,
        ))
    assert summary == "FINAL SUMMARY"
    assert n == 3
    assert calls == 1
    assert m.call_count == 1


def test_12_large_document_multi_batch():
    # 30 chunks x ~450 tokens each exceeds BATCH_MAX_TOKENS -> several map batches.
    chunks = [_rk(i, text=("This paragraph discusses operational policy and visitor metrics. " * 30)) for i in range(30)]
    captured = []

    async def fake_chat(system, user, max_tokens=700, temperature=0.2):
        captured.append(system)
        return "PART" if "section summary" in system else "FINAL"

    with patch("document_summarizer.nim_client.chat", side_effect=fake_chat) as m:
        summary, n, calls = run(S.summarize_document(
            chunks, {"id": "a", "title": "T", "filename": "0067-pdf.pdf"}, False,
        ))
    assert summary == "FINAL"
    assert n == 30
    assert m.call_count >= 3          # map(s) + final
    assert any("section summary" in s for s in captured)


def test_13_recursive_reduction_large_document(monkeypatch):
    monkeypatch.setattr(S, "REDUCE_MAX_TOKENS", 300)  # small -> forces reduce rounds
    chunks = [_rk(i, text=("The annual report describes impact, operations, and policy directions. " * 30)) for i in range(60)]
    reduce_calls = []

    async def fake_chat(system, user, max_tokens=700, temperature=0.2):
        # Dispatch on the most specific stage markers FIRST: the map prompt also
        # contains "summary of ONE authorized document", so check map before final.
        if "condensing" in system:
            reduce_calls.append(system)
            return "CONDENSED " + ("x " * 30)
        if "section summary" in system:
            return "The section recaps key findings, operational metrics, and forward-looking policy. " * 5
        return "THE FINAL SUMMARY"

    with patch("document_summarizer.nim_client.chat", side_effect=fake_chat):
        summary, _, calls = run(S.summarize_document(
            chunks, {"id": "a", "title": "T", "filename": "0067-pdf.pdf"}, False,
        ))
    assert summary == "THE FINAL SUMMARY"
    assert reduce_calls, "reduce pass was never invoked for an over-budget document"
    assert calls <= S.MAX_REDUCE_LEVELS * 60  # bounded depth, never one call per chunk


def test_14_citation_source_identity_integrity():
    """One doc citation only; in-text 'Museums Change Lives' is content, never a source."""
    filedoc = docrow("a1", "Museums Matter, 2015", "0067-pdf.pdf", ["manager"])
    db = FakeDb([
        FakeResult([filedoc]),
        FakeResult([chunkrow(i, "a1", i, f"mentions Museums Change Lives doc {i}", ["manager"]) for i in range(8)]),
    ])

    async def fake_chat(system, user, max_tokens=700, temperature=0.2):
        assert "INSIDE the supplied text" in system  # source-grounding rule present
        return "A summary of the authorized document."

    with patch("document_summarizer.nim_client.chat", side_effect=fake_chat):
        resp = run(_handle_document_summary(db, "conv-1", user_row(), "summarize 0067", "manager", False))

    am = resp.assistant_message
    rd = am.retrieval_detail
    assert rd["pipeline"]["mode"] == "document_summary"
    assert rd["pipeline"]["filename"] == "0067-pdf.pdf"
    assert len(am.citations) == 1
    assert am.citations[0]["title"] == "Museums Matter, 2015"
    assert am.citations[0]["source"] == "0067-pdf.pdf"
    assert all(c.get("title") != "Museums Change Lives" for c in am.citations)
    assert len(rd["retrieved"]) <= 5   # bounded frontend payload
    assert rd["pipeline"]["chunk_count"] == 8


# ---------------- routing / handler behavior ----------------


def test_15_inventory_regression():
    q = "What documents are in the knowledge base?"
    assert R.is_inventory_question(q) is True
    assert R.is_document_summary_question(q) is False


def test_16_normal_rag_regression():
    q = "How many documents mention the Mendoza Review?"
    assert R.is_inventory_question(q) is False
    assert R.is_document_summary_question(q) is False


def test_17_contextual_summarize_report_only_when_unique():
    db = FakeDb([FakeResult([msgrow([], {"retrieved": [{"document_id": "d1"}]})])])
    assert run(_context_document_id(db, "conv1")) == "d1"
    db2 = FakeDb([FakeResult([
        msgrow([{"document_id": "d1"}]),
        msgrow([], {"retrieved": [{"document_id": "d2"}]}),
    ])])
    assert run(_context_document_id(db2, "conv1")) == "__ambiguous__"
    db3 = FakeDb([FakeResult([])])
    assert run(_context_document_id(db3, "conv1")) is None


def test_security_inaccessible_document_gets_safe_response():
    """Non-authorized user receives the same vague no-match for a similar filename."""
    db = FakeDb([
        FakeResult([docrow("h", "Visible", "0068.pdf", ["hr"])]),
    ])
    with patch("routers.chat_router.nim_client.chat"):
        resp = run(_handle_document_summary(db, "conv-1", user_row(), "summarize the 0067 pdf", "hr", False))
    am = resp.assistant_message
    assert am.retrieval_detail["pipeline"]["mode"] == "document_summary"
    assert am.retrieval_detail["pipeline"]["reason"] == "no_match"
    assert "don't have access to a document" in am.content.lower()
    assert "0067-pdf.pdf" not in am.content          # no existence/filename leak
    assert am.citations == []                         # no citation leak


def test_document_summary_never_touches_rag_path():
    """Summary path must not call dense/BM25/rerank."""
    db = FakeDb([
        FakeResult([docrow("a1", "T", "0067-pdf.pdf", ["manager"])]),
        FakeResult([chunkrow(1, "a1", 0, "some content", ["manager"])]),
    ])
    with patch("document_summarizer.nim_client.chat") as chat, \
         patch("retrieval._dense_retrieve", side_effect=AssertionError("dense called")), \
         patch("retrieval._lexical_retrieve", side_effect=AssertionError("bm25 called")), \
         patch("routers.chat_router.rerank", side_effect=AssertionError("rerank called")):
        resp = run(_handle_document_summary(
            db, "conv-1", user_row(), "summarize the 067 pdf", "manager", False,
        ))
    assert resp.assistant_message.retrieval_detail["pipeline"]["mode"] == "document_summary"


def test_contextual_summary_resolves_single_document():
    """'summarize the report' after ONE doc was cited resolves to it, re-checking RBAC."""
    ctx_rows = [msgrow([{"document_id": "d1", "title": "T1"}])]
    db = FakeDb([
        FakeResult(ctx_rows),                           # _context_document_id
        FakeResult([docrow("d1", "T", "0067-pdf.pdf", ["manager"])]),  # resolve_document_by_id
        FakeResult([chunkrow(1, "d1", 0, "content one", ["manager"]),
                    chunkrow(2, "d1", 1, "content two", ["manager"])]),  # chunks
    ])
    with patch("document_summarizer.nim_client.chat", side_effect=lambda *a, **k: "CONTEXTUAL SUMMARY"):
        resp = run(_handle_document_summary(db, "conv-1", user_row(), "summarize the report", "manager", False))
    am = resp.assistant_message
    assert am.retrieval_detail["pipeline"]["mode"] == "document_summary"
    assert am.content == "CONTEXTUAL SUMMARY"
    assert am.retrieval_detail["pipeline"]["filename"] == "0067-pdf.pdf"
    assert any("acl_principals && :principals" in s for s in db.statements)
    assert any("tenant_id = CAST(:tenant AS uuid)" in s for s in db.statements)


# ---------------- section-scoped summaries ("summarize the abstract") ----------------


def test_section_extraction():
    assert R.document_section("Summarize the abstract") == "abstract"
    assert R.document_section("Summarize the abstract of 1706.03762v7.pdf") == "abstract"
    assert R.document_section("summarize the conclusion of 0067") == "conclusion"
    assert R.document_section("summarize the 067 pdf") is None
    assert R.document_section("summarize the report") is None
    assert R.document_section("What documents are in the knowledge base?") is None


def test_section_only_question_routes_to_summary_path():
    assert R.is_document_summary_question("Summarize the abstract") is True
    assert R.is_document_summary_question("summarize the introduction of 0067-pdf.pdf") is True
    # No summary intent -> stays on the normal RAG path even with a section word.
    assert R.is_document_summary_question("What does the introduction say about X?") is False
    assert R.is_document_summary_question("How many documents mention the Mendoza Review?") is False


def test_select_section_chunks_contiguous_run():
    abstract = _rk(0, text=(
        "Attention Is All You Need\n\nAbstract\n\n"
        "We propose the Transformer, a sequence transduction model based entirely on attention. "
    ))
    intro = _rk(1, text="1 Introduction\n\nRecurrent neural models dominate sequence transduction. ")
    arch = _rk(2, text="2 Model Architecture\n\nMost competitive models are encoder-decoders. ")
    chunks = [abstract, intro, arch]

    sel = S.select_section_chunks(chunks, "abstract")
    assert [c.chunk_index for c in sel] == [0]

    sel_intro = S.select_section_chunks(chunks, "introduction")
    assert [c.chunk_index for c in sel_intro] == [1]  # stops before "2 Model Architecture"


def test_select_section_chunks_multi_chunk_and_caps():
    sec0 = _rk(0, text="Introduction\n\nFirst part of the introduction. ")
    sec1 = _rk(1, text="More introduction detail without any heading. ")
    next_sec = _rk(2, text="Conclusion\n\nWrap up. ")
    sel = S.select_section_chunks([sec0, sec1, next_sec], "introduction")
    assert [c.chunk_index for c in sel] == [0, 1]


def test_select_section_chunks_not_found_returns_none():
    chunks = [_rk(i, text="plain body text with no headings whatsoever. ") for i in range(3)]
    assert S.select_section_chunks(chunks, "abstract") is None
    assert S.select_section_chunks([], "abstract") is None


def test_summarize_section_prompt_and_scope():
    captured = []

    async def fake_chat(system, user, max_tokens=700, temperature=0.2):
        captured.append((system, user))
        return "ABSTRACT SUMMARY"

    with patch("document_summarizer.nim_client.chat", side_effect=fake_chat):
        chunks = [
            _rk(0, text="Abstract\n\nWe propose the Transformer model. "),
            _rk(1, text="1 Introduction\n\nRecurrent models are slow. "),
        ]
        sel = S.select_section_chunks(chunks, "abstract")
        summary, n, calls = run(S.summarize_document(
            sel, {"id": "a", "title": "T", "filename": "1706.03762v7.pdf"}, False, section="abstract",
        ))
    assert summary == "ABSTRACT SUMMARY"
    assert n == 1 and calls == 1
    system, user = captured[0]
    assert "'abstract'" in system                      # section-restricted prompt
    assert "1 Introduction" not in user                # out-of-section content never sent


def test_handler_section_scoped_summary_end_to_end():
    filedoc = docrow("a1", "Attention Paper", "1706.03762v7.pdf", ["manager"])
    db = FakeDb([
        FakeResult([filedoc]),
        FakeResult([
            chunkrow(1, "a1", 0, "Attention Is All You Need\n\nAbstract\n\nWe propose the Transformer model.", ["manager"]),
            chunkrow(2, "a1", 1, "1 Introduction\n\nRecurrent models dominate sequence transduction.", ["manager"]),
        ]),
    ])

    async def fake_chat(system, user, max_tokens=700, temperature=0.2):
        assert "'abstract'" in system
        assert "1 Introduction" not in user
        return "The paper introduces the Transformer, an attention-only architecture."

    with patch("document_summarizer.nim_client.chat", side_effect=fake_chat):
        resp = run(_handle_document_summary(
            db, "conv-1", user_row(), "summarize the abstract of 1706.03762v7.pdf", "manager", False,
        ))

    am = resp.assistant_message
    rd = am.retrieval_detail
    assert rd["pipeline"]["section"] == "abstract"
    assert rd["pipeline"]["section_found"] is True
    assert rd["pipeline"]["chunk_count"] == 1          # ONLY the abstract chunk summarized
    assert "Transformer" in am.content
    # RBAC SQL still ran before any summarization happened.
    assert any("acl_principals && :principals" in s and "tenant_id = CAST(:tenant AS uuid)" in s
               for s in db.statements)


def test_handler_section_not_found_falls_back_to_full_document():
    filedoc = docrow("a1", "Plain Doc", "0067-pdf.pdf", ["manager"])
    db = FakeDb([
        FakeResult([filedoc]),
        FakeResult([
            chunkrow(1, "a1", 0, "body text without headings one", ["manager"]),
            chunkrow(2, "a1", 1, "body text without headings two", ["manager"]),
        ]),
    ])

    async def fake_chat(system, user, max_tokens=700, temperature=0.2):
        assert "'abstract'" not in system  # fallback prompt must not pretend a section exists
        return "FULL DOCUMENT SUMMARY"

    with patch("document_summarizer.nim_client.chat", side_effect=fake_chat):
        resp = run(_handle_document_summary(
            db, "conv-1", user_row(), "summarize the abstract of 0067-pdf.pdf", "manager", False,
        ))

    rd = resp.assistant_message.retrieval_detail
    assert rd["pipeline"]["section"] == "abstract"
    assert rd["pipeline"]["section_found"] is False
    assert rd["pipeline"]["chunk_count"] == 2          # whole document summarized honestly
    assert resp.assistant_message.content == "FULL DOCUMENT SUMMARY"


# ---------------- tenant isolation + principal ACLs + audit log ----------------


def _admin(tenant=TENANT_A):
    return {"id": "admin-1", "email": "a@x.io", "role": "admin", "status": "approved",
            "must_change_password": False, "created_at": "2026-01-01T00:00:00Z", "tenant_id": tenant}


def test_tenant_filter_on_chunk_reads_and_admin_bypass():
    """Every chunk read is tenant-scoped; bypass drops only the principals check."""
    db = FakeDb()
    run(R.document_chunks(db, "doc-1", role="hr", admin_bypass=False, tenant=TENANT_A))
    sql = db.statements[0]
    assert "c.tenant_id = CAST(:tenant AS uuid)" in sql
    assert "c.acl_principals && :principals" in sql
    assert db.params[0]["tenant"] == TENANT_A

    db2 = FakeDb()
    run(R.document_chunks(db2, "doc-1", role="admin", admin_bypass=True, tenant=TENANT_A))
    sql2 = db2.statements[0]
    assert "c.tenant_id = CAST(:tenant AS uuid)" in sql2   # bypass keeps tenant scoping
    assert "acl_principals &&" not in sql2                  # ...and skips only the principals filter
    assert db2.params[0]["tenant"] == TENANT_A


def test_dense_and_lexical_bypass_stay_tenant_scoped():
    db = FakeDb()
    run(R._dense_retrieve(db, "[0.1,0.2]", "admin", True, tenant=TENANT_A))
    assert len(db.statements) == 1
    assert "c.tenant_id = CAST(:tenant AS uuid)" in db.statements[0]
    assert "acl_principals &&" not in db.statements[0]

    db2 = FakeDb()
    run(R._lexical_retrieve(db2, "insurance policy details", "admin", True, tenant=TENANT_A))
    assert "c.tenant_id = CAST(:tenant AS uuid)" in db2.statements[0]
    assert "acl_principals &&" not in db2.statements[0]


def test_user_tenant_a_cannot_reach_tenant_b_documents():
    """Resolution/inventory queries carry the caller's tenant, so tenant-B rows
    can never match — not even with a byte-identical role. A cross-tenant
    document is indistinguishable from a nonexistent one (no metadata leak)."""
    db = FakeDb()
    run(R.resolve_document(db, {"kind": "filename", "value": "b.pdf"}, "manager", False, tenant=TENANT_A))
    sql = db.statements[0]
    assert "tenant_id = CAST(:tenant AS uuid)" in sql
    assert "acl_principals && :principals" in sql
    assert db.params[0]["tenant"] == TENANT_A

    # Admin resolution is tenant-scoped too (bypass keeps the tenant filter).
    db2 = FakeDb()
    run(R.resolve_document(db2, {"kind": "filename", "value": "b.pdf"}, "admin", True, tenant=TENANT_A))
    assert "tenant_id = CAST(:tenant AS uuid)" in db2.statements[0]
    assert db2.params[0]["tenant"] == TENANT_A


def test_assert_rbac_flags_cross_tenant_chunk_like_role_mismatch():
    ours = _rk(1)
    R.assert_rbac([ours], role="manager", tenant=DEFAULT_TENANT)       # same tenant: ok
    foreign = _rk(2, tenant=TENANT_B)
    with pytest.raises(RuntimeError):
        R.assert_rbac([foreign], role="manager", tenant=DEFAULT_TENANT)  # cross-tenant: raises
    # Admin bypass (tenant enforced in SQL) still skips the in-memory check.
    R.assert_rbac([foreign], role="manager", admin_bypass=True)


def test_acl_version_visible_on_chunk_read_path():
    db = FakeDb([FakeResult([chunkrow(7, "d1", 0, "content", ["manager"], acl_version=9)])])
    chunks = run(R.document_chunks(db, "d1", role="manager", admin_bypass=False, tenant=DEFAULT_TENANT))
    assert chunks[0].acl_version == 9
    assert chunks[0].acl_principals == ["role:manager"]
    assert chunks[0].tenant_id == DEFAULT_TENANT


def test_acl_update_bumps_version_and_writes_audit():
    db = FakeDb([
        FakeResult([docrow("d1", "T", "0067-pdf.pdf", ["manager"])]),          # old roles
        FakeResult([docrow("d1", "T", "0067-pdf.pdf", ["manager", "hr"])]),  # UPDATE ... RETURNING
    ])
    run(AR.update_document_roles("d1", UpdateDocRolesRequest(allowed_roles=["manager", "hr"]), _admin(), db))
    joined = "\n".join(db.statements)
    assert "acl_version = acl_version + 1" in joined          # document bumped
    assert joined.count("acl_version = acl_version + 1") >= 2  # chunks bumped too
    assert "acl_principals = :p" in joined
    audits = [p for p in db.params if p and p.get("act") == "acl.update"]
    assert audits, "no audit row written for acl.update"
    ap = audits[0]
    assert ap["tt"] == "document" and ap["ti"] == "d1"
    assert ap["t"] == TENANT_A and ap["a"] == "admin-1"
    assert json.loads(ap["d"])["new_roles"] == ["hr", "manager"]
    assert json.loads(ap["d"])["old_roles"] == ["manager"]


def test_chunk_acl_update_bumps_version_and_audits():
    db = FakeDb([
        FakeResult([docrow("d1", "T", "0067.pdf", ["manager"])]),                      # candidate
        # UPDATE ... RETURNING row (id is the chunks bigserial id here)
        FakeResult([types.SimpleNamespace(
            id=7, chunk_index=0, content="content", allowed_roles=["manager"],
            roles_ai_suggested=False, source_page=1,
        )]),
    ])
    run(AR.update_chunk_roles("d1", 7, UpdateChunkRolesRequest(allowed_roles=["manager"]), _admin(), db))
    joined = "\n".join(db.statements)
    assert "acl_version = acl_version + 1" in joined
    audits = [p for p in db.params if p and p.get("act") == "chunk.acl.update"]
    assert audits and audits[0]["tt"] == "chunk" and audits[0]["ti"] == "7"
    assert json.loads(audits[0]["d"])["old_roles"] == ["manager"]


def test_audit_log_written_on_publish_and_delete():
    db = FakeDb([FakeResult([docrow("d1", "T", "0067.pdf", ["manager"], status="published")])])
    run(AR.publish_document("d1", _admin(), db))
    audits = [p for p in db.params if p and p.get("act") == "document.publish"]
    assert audits and audits[0]["tt"] == "document" and audits[0]["ti"] == "d1"
    assert audits[0]["t"] == TENANT_A and audits[0]["a"] == "admin-1"

    deleted = types.SimpleNamespace(id="d1", title="T", filename="0067.pdf", tenant_id=TENANT_A)
    db2 = FakeDb([FakeResult([deleted])])
    out = run(AR.delete_document("d1", _admin(), db2))
    assert out == {"deleted": True, "id": "d1"}
    audits2 = [p for p in db2.params if p and p.get("act") == "document.delete"]
    assert audits2 and audits2[0]["ti"] == "d1"
    # The delete audit names the DELETED doc's tenant (same as the admin's here).
    assert audits2[0]["t"] == TENANT_A


def test_upload_stamps_tenant_principals_and_audits():
    db = FakeDb([FakeResult([docrow("d9", "T", "f.pdf", ["manager"])])])  # INSERT ... RETURNING
    run(AR._persist_document(
        db, "T", "f.pdf", "admin-1", ["manager"],
        [("chunk text", 1)], [[0.1, 0.2, 0.3, 0.4]], [["manager"]],
        tenant_id=TENANT_A,
    ))
    joined = "\n".join(db.statements)
    assert "INSERT INTO documents" in joined and "tenant_id" in joined
    assert "INSERT INTO chunks" in joined and "acl_principals" in joined
    doc_insert, chunk_insert = db.params[0], db.params[1]
    assert doc_insert["p"] == ["role:manager"] and doc_insert["tn"] == TENANT_A
    assert chunk_insert["p"] == ["role:manager"] and chunk_insert["tn"] == TENANT_A
    audits = [p for p in db.params if p and p.get("act") == "document.upload"]
    assert audits and audits[0]["t"] == TENANT_A and audits[0]["a"] == "admin-1"
    assert json.loads(audits[0]["d"])["chunk_count"] == 1


def test_cross_tenant_admin_document_ops_return_404():
    """Admin mutations are tenant-scoped: a foreign-tenant doc resolves to 404
    (indistinguishable from nonexistent), never to a successful cross-tenant write."""
    db = FakeDb()  # no rows -> SELECT/UPDATE/DELETE finds nothing for tenant A
    with pytest.raises(Exception):
        run(AR.publish_document("d-b", _admin(tenant=TENANT_A), db))
    assert "tenant_id = CAST(:t AS uuid)" in db.statements[0]


# ---------------- follow-up: user endpoints + chunk-listing tenant scoping ----------------


def _userrow(uid, email, role, status, tenant=TENANT_A):
    return types.SimpleNamespace(
        id=uid, email=email, role=role, status=status,
        must_change_password=False, created_at=datetime(2026, 1, 1), tenant_id=tenant,
    )


class TenantFilteringFakeDb(FakeDb):
    """FakeDb that emulates the real SQL tenant filter for profiles/documents
    result rows, so tests can prove tenant-B rows in the fixture are NOT
    returned to a tenant-A admin (the plain FakeDb returns everything)."""

    async def execute(self, stmt, params=None):
        self.statements.append(str(stmt))
        self.params.append(dict(params) if params else None)
        s = str(stmt)
        result = self._queue.pop(0) if self._queue else FakeResult()
        tenant = (params or {}).get("t")
        if tenant and hasattr(result, "_rows"):
            result._rows = [r for r in result._rows if str(getattr(r, "tenant_id", "")) == tenant]
        return result


def test_list_document_chunks_cross_tenant_404_not_content():
    """Gap 1 regression: a tenant-A admin listing chunks of a tenant-B document
    gets a 404 — never the chunk content."""
    db = FakeDb()  # existence check finds no tenant-A document -> 404
    with pytest.raises(HTTPException) as exc:
        run(AR.list_document_chunks("doc-b", _admin(tenant=TENANT_A), db))
    assert exc.value.status_code == 404
    joined = "\n".join(db.statements)
    assert "d.tenant_id = CAST(:t AS uuid)" in joined        # chunks query scoped
    assert "tenant_id = CAST(:t AS uuid)" in joined          # existence check scoped
    assert db.params[0]["t"] == TENANT_A and db.params[1]["t"] == TENANT_A


def test_list_document_chunks_returns_own_tenant_chunks():
    chunk = types.SimpleNamespace(
        id=7, chunk_index=0, content="own-tenant chunk content", allowed_roles=["manager"],
        roles_ai_suggested=True, source_page=1, filename="0067.pdf",
    )
    exists_row = types.SimpleNamespace(tenant_id=TENANT_A)
    db = FakeDb([FakeResult([chunk]), FakeResult([exists_row])])
    out = run(AR.list_document_chunks("d1", _admin(tenant=TENANT_A), db))
    assert len(out) == 1 and out[0].content == "own-tenant chunk content"
    assert "d.tenant_id = CAST(:t AS uuid)" in db.statements[0]
    assert db.params[0]["t"] == TENANT_A


def test_list_users_tenant_scoped_even_when_tenant_b_users_exist():
    """Gap 2 regression: a tenant-A admin sees ONLY tenant-A users, even though
    tenant-B users exist in the fixture data."""
    users = [
        _userrow("u-a1", "a1@x.io", "manager", "approved", tenant=TENANT_A),
        _userrow("u-b1", "b1@other.io", "admin", "approved", tenant=TENANT_B),
        _userrow("u-b2", "b2@other.io", "hr", "pending", tenant=TENANT_B),
    ]
    db = TenantFilteringFakeDb([FakeResult(users)])
    out = run(AR.list_users(_admin(tenant=TENANT_A), db))
    assert [u.id for u in out] == ["u-a1"]          # tenant-B users invisible
    assert all("other.io" not in u.email for u in out)
    assert "tenant_id = CAST(:t AS uuid)" in db.statements[0]
    assert db.params[0]["t"] == TENANT_A


def test_user_mutations_cross_tenant_404_and_never_touch_target():
    """A tenant-A admin cannot approve or promote a tenant-B user: 404, no
    audit row, and the fixture's target user row is untouched."""
    target = _userrow("u-b1", "b1@other.io", "employee", "pending", tenant=TENANT_B)

    db = FakeDb()  # tenant-scoped SELECT finds nothing -> 404, no UPDATE at all
    with pytest.raises(HTTPException) as exc:
        run(AR.approve_user("u-b1", ApproveUserRequest(role="admin"), _admin(tenant=TENANT_A), db))
    assert exc.value.status_code == 404
    assert "tenant_id = CAST(:t AS uuid)" in db.statements[0]
    assert db.params[0]["t"] == TENANT_A
    assert not any("UPDATE profiles" in s for s in db.statements)   # never mutated
    assert not any("INSERT INTO audit_log" in s for s in db.statements)

    db2 = FakeDb()  # same for change_user_role
    with pytest.raises(HTTPException) as exc2:
        run(AR.change_user_role("u-b1", ApproveUserRequest(role="admin"), _admin(tenant=TENANT_A), db2))
    assert exc2.value.status_code == 404
    assert not any("UPDATE profiles" in s for s in db2.statements)
    # target row unchanged (the handler never got past the scoped SELECT)
    assert (target.role, target.status) == ("employee", "pending")


def test_user_approve_and_role_update_are_audited():
    old = _userrow("u-a1", "a1@x.io", "employee", "pending", tenant=TENANT_A)
    updated = _userrow("u-a1", "a1@x.io", "manager", "approved", tenant=TENANT_A)

    # approve_user
    db = FakeDb([FakeResult([old]), FakeResult([updated])])
    out = run(AR.approve_user("u-a1", ApproveUserRequest(role="manager"), _admin(tenant=TENANT_A), db))
    assert out.role == "manager" and out.status == "approved"
    audits = [p for p in db.params if p and p.get("act") == "user.approve"]
    assert audits and audits[0]["tt"] == "user" and audits[0]["ti"] == "u-a1"
    assert audits[0]["t"] == TENANT_A and audits[0]["a"] == "admin-1"
    detail = json.loads(audits[0]["d"])
    assert detail["old_role"] == "employee" and detail["new_role"] == "manager"
    assert detail["old_status"] == "pending" and detail["new_status"] == "approved"

    # change_user_role
    old2 = _userrow("u-a1", "a1@x.io", "manager", "approved", tenant=TENANT_A)
    updated2 = _userrow("u-a1", "a1@x.io", "hr", "approved", tenant=TENANT_A)
    db2 = FakeDb([FakeResult([old2]), FakeResult([updated2])])
    run(AR.change_user_role("u-a1", ApproveUserRequest(role="hr"), _admin(tenant=TENANT_A), db2))
    audits2 = [p for p in db2.params if p and p.get("act") == "user.role_update"]
    assert audits2 and audits2[0]["tt"] == "user" and audits2[0]["ti"] == "u-a1"
    detail2 = json.loads(audits2[0]["d"])
    assert detail2["old_role"] == "manager" and detail2["new_role"] == "hr"


# ---------------- persisted full-text lexical leg (migration 004) ----------------


def test_lexical_matches_ranks_limits_inside_postgres():
    """The lexical leg is one SQL statement doing TRUE BM25 (not ts_rank_cd):
    term-frequency table + doclen + corpus-aware IDF, ORDER BY score, LIMIT."""
    db = FakeDb()
    run(R._lexical_retrieve(db, "policy 44-B/2026 premium", "manager", False, tenant=TENANT_A))
    assert len(db.statements) == 1                     # single round trip
    sql = db.statements[0]
    # BM25 machinery is in the SQL...
    assert "chunk_terms" in sql
    assert "c.doclen" in sql
    assert "ln((s.total_docs - i.doc_freq + 0.5) / (i.doc_freq + 0.5))" in sql   # IDF
    assert "t.tf * (1.5 + 1)) / (t.tf + 1.5 * (1 - 0.75" in sql                   # k1=1.5,b=0.75
    assert "avg_doclen" in sql
    assert "GROUP BY t.chunk_id, a.doclen" in sql
    assert "ORDER BY sc.bm25_score DESC" in sql
    assert "LIMIT :k" in sql
    # ...and ts_rank_cd / tsvector / tsquery are NOT.
    for banned in ("ts_rank_cd", "search_vector", "to_tsquery", "websearch_to_tsquery", "ts_rank"):
        assert banned not in sql, f"lexical leg must not use {banned}"
    # IDF is computed over the AUTHORIZED corpus only (tf restricted to auth),
    # so cross-tenant term rows can never inflate doc_freq.
    assert "JOIN auth a ON a.id = ct.chunk_id" in sql
    # tenant/ACL filter shape unchanged by the rewrite
    assert "c.tenant_id = CAST(:tenant AS uuid)" in sql
    assert "c.acl_principals && :principals" in sql
    assert "d.status = 'published'" in sql
    # Query terms go through a typed bind param (:terms), not into SQL text.
    assert db.params[0]["terms"] == ["policy", "44", "b", "2026", "premium"]
    assert db.params[0]["k"] == R.LEXICAL_K
    assert db.params[0]["tenant"] == TENANT_A


def test_lexical_terms_bind_param_is_injection_safe():
    """Only [a-z0-9]+ tokens reach the :terms bind param — no operators,
    quotes, keyword punctuation, or SQL can be smuggled into the query text."""
    db = FakeDb()
    run(R._lexical_retrieve(db, "premium'); DROP TABLE chunks; --", "manager", False, tenant=TENANT_A))
    sql = db.statements[0]
    assert db.params[0]["terms"] == ["premium", "drop", "table", "chunks"]
    assert "DROP" not in sql.upper()
    assert "chunks; --" not in sql.lower()
    assert ":terms" in sql   # tokens appear only behind the bind placeholder


def test_lexical_admin_bypass_tenant_scoped_bm25():
    db = FakeDb()
    run(R._lexical_retrieve(db, "insurance policy details", "admin", True, tenant=TENANT_A))
    sql = db.statements[0]
    assert "c.tenant_id = CAST(:tenant AS uuid)" in sql       # bypass keeps tenant scoping
    assert "acl_principals &&" not in sql                      # and skips only principals
    assert "d.status = 'published'" not in sql                 # (status too)
    # Real BM25 either way
    assert "chunk_terms" in sql and "ln((s.total_docs" in sql
    assert "ts_rank_cd" not in sql
    assert "LIMIT :k" in sql
    assert db.params[0]["tenant"] == TENANT_A


def test_lexical_empty_query_short_circuits_without_round_trip():
    """Empty / punctuation-only queries short-circuit — no SQL at all."""
    db = FakeDb()
    for q in ("", "   ", "!!! ??? ...", None):
        assert run(R._lexical_retrieve(db, q, "manager", False, tenant=TENANT_A)) == []
    assert db.statements == []


def test_lexical_rows_arrive_in_sql_rank_order():
    """SQL returns BM25-ranked rows; the app assigns lexical_rank by arrival
    order. RRF consumes the rank positions (not the score) — the BM25 value is
    carried as metadata only."""
    def row(cid, score):
        return types.SimpleNamespace(
            chunk_id=cid, document_id="d1", chunk_index=0, source_page=1,
            content=f"content {cid}", allowed_roles=["manager"],
            acl_principals=["role:manager"], acl_version=3, tenant_id=TENANT_A,
            doc_title="T", source="0067.pdf", score=score,
        )
    db = FakeDb([FakeResult([row(2, 2.7), row(1, 1.2), row(9, 0.4)])])
    chunks = run(R._lexical_retrieve(db, "anything", "manager", False, tenant=TENANT_A, k=3))
    assert [c.id for c in chunks] == ["2", "1", "9"]          # SQL order preserved
    assert [c.lexical_rank for c in chunks] == [1, 2, 3]       # what RRF actually consumes
    assert chunks[0].bm25_score == pytest.approx(2.7)          # genuine BM25 score, metadata only
    assert chunks[0].acl_version == 3
    assert chunks[0].acl_principals == ["role:manager"]


def test_rank_bm25_dependency_removed():
    """The in-process BM25 implementation is gone (a docstring mention of the
    old scorer is fine — the import and any BM25Okapi call are not)."""
    assert not hasattr(R, "_tokenize")
    import inspect
    src = inspect.getsource(R)
    assert "from rank_bm25" not in src
    assert "BM25Okapi(" not in src
