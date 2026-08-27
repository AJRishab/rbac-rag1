"""Tests for the document-summary scope (third pipeline path).

Covers detection, safe document resolution, RBAC enforcement (no unauthorized
leaks), document-scoped chunk retrieval, hierarchical summarization, citation
integrity, contextual references, and regressions for corpus-inventory and
normal RAG. Uses fake DB results and patched NIM calls - no live network.
"""
import asyncio
import types
from unittest.mock import patch

import pytest

import retrieval as R
import document_summarizer as S
from routers.chat_router import _handle_document_summary, _context_document_id


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
    """Queued results + captured SQL statements for the async code paths."""

    def __init__(self, queue=None, statements=None):
        self._queue = list(queue or [])
        self.statements = statements if statements is not None else []

    async def execute(self, stmt, params=None):
        self.statements.append(str(stmt))
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


def docrow(did, title, filename, roles=None, status="published"):
    return types.SimpleNamespace(
        id=did, title=title, filename=filename,
        allowed_roles=roles or [], status=status,
    )


def chunkrow(cid, did, idx, content, roles=None, page=None):
    return types.SimpleNamespace(
        chunk_id=cid, document_id=did, chunk_index=idx, source_page=page,
        content=content, allowed_roles=roles or [],
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


def _rk(i, roles=None, text=None):
    """RetrievedChunk helper."""
    return R.RetrievedChunk(
        id=str(i), document_id="d1", chunk_index=i,
        content=text or f"chunk number {i} with body text to pad the token count. " * 8,
        allowed_roles=roles or ["manager"], title="Museums Matter, 2015",
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
    assert "allowed_roles && ARRAY[:role]" in sql


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
    assert "c.allowed_roles && :r" in sql
    db2 = FakeDb()
    run(R.document_chunks(db2, "doc-1", role="admin", admin_bypass=True))
    sql2 = db2.statements[0]
    assert "allowed_roles &&" not in sql2
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
    assert "allowed_roles && ARRAY[:role]" in db2.statements[0]


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

    with patch("document_summarizer.openrouter.chat", side_effect=fake_chat) as m:
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

    with patch("document_summarizer.openrouter.chat", side_effect=fake_chat) as m:
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

    with patch("document_summarizer.openrouter.chat", side_effect=fake_chat):
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

    with patch("document_summarizer.openrouter.chat", side_effect=fake_chat):
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
    with patch("routers.chat_router.openrouter.chat"):
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
    with patch("document_summarizer.openrouter.chat") as chat, \
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
    with patch("document_summarizer.openrouter.chat", side_effect=lambda *a, **k: "CONTEXTUAL SUMMARY"):
        resp = run(_handle_document_summary(db, "conv-1", user_row(), "summarize the report", "manager", False))
    am = resp.assistant_message
    assert am.retrieval_detail["pipeline"]["mode"] == "document_summary"
    assert am.content == "CONTEXTUAL SUMMARY"
    assert am.retrieval_detail["pipeline"]["filename"] == "0067-pdf.pdf"
    assert any("allowed_roles && ARRAY[:role]" in s for s in db.statements)
