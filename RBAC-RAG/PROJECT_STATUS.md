# Project Status & Orientation

**Last updated:** Aug 2026 · Tracks: what exists today, what is known to be missing, and what is next.

This document is the single source of truth for "how far along are we". The old
`plan.md` and `audit_findings.md` are archived under [`archive/`](archive/) because they
described an earlier stage of the project and had drifted from the code.

## Headline status

The core loop is **complete and real (no mocks)**:

- Upload → parse → chunk → embed → **NIM suggests roles per chunk** → admin review → publish.
- Ask → embed → **role-filtered vector search inside SQL** → citations + `retrieved`/`blocked` counters → NIM chat answer.
- Supabase Auth (JWT verified in the backend via JWKS) backs login, and `profiles`
  records drive approval + roles.

The current repository is the **permission-aware ("Sentry RAG") version of the
app**. The older "allow-all" prototype presented in the original README is history.

---

## What is built (verified in code)

**Backend (FastAPI)**
- `server.py` entrypoint: mounts `/api`, per-router flow, SPA static serving
  (`FRONTEND_BUILD_DIR`), default `CORS_ORIGINS` of `https://rbac-rag-nine.vercel.app`.
- **Auth**: DEP signed JWT verification against Supabase JWKS; deps
  `require_approved` gating on `profiles.role` + `profiles.status`.
- **SQL schema** (created on startup): `profiles` (linked to `auth.users`),
  `documents` (`status` = `pending_review` / `published`), `chunks`
  (`embedding vector(2048)`, `allowed_roles text[]`, `roles_ai_suggested bool`),
  `conversations`, `messages` (persists `citations`, `retrieval_detail`,
  `retrieved_count`, `blocked_count`), plus a `handle_new_user` trigger
  creating a `profiles` row on Supabase signup.
- **Ingest** (`ingest.py`): txt/md/markdown/pdf/docx up to 20 MB; markdown
  formatting preserved; ~500-token chunks with 50-token overlap (tiktoken); embed
  via Nemotron-3 Embed → 2048-dim.
- **NIM client** (`nim_client.py`): lazy client init, retry + 429 handling,
  `embed()`, `chat()`, `suggest_chunk_roles()` (single batched LLM call sized by
  `NIM_CHUNK_ROLE_BATCH_CHARS`, falls back to the doc's candidate roles on error).
- **Hybrid retrieval + rerank** (in `retrieval.py` + `reranker.py`, wired via
  `chat_router`): dense pgvector cosine `AND` in-process `rank_bm25` lexical legs,
  **both RBAC-filtered inside SQL** (`allowed_roles && ARRAY[:role]`, admins bypass),
  fused with RRF, then a NIM cross-encoder reranker narrows top-20 → top-k. A
  post-fusion `assert_rbac()` defense-in-depth check raises loudly if an
  unauthorized chunk ever reaches memory; `retrieval_detail` records
  `dense_rank`/`lexical_rank`/`rrf_score`/`rerank_score`/`rerank_rank`.
- **Admin CRUD** (`admin_router`): users list/approve/role; documents
  list/upload/chunks/publish/`reset-chunk-roles`/delete; per-chunk `PATCH`
  to edit `allowed_roles`.

**Frontend (React, CRA + craco, Tailwind, shadcn/ui)**
- Supabase auth (anon key URL/login), admin documents & chunks browser, admin
  users page, chat UI with per-answer **Retrieval Detail panel** (retrieved vs
  blocked + admin-bypass flag).
- Capacitor Android wrapper + deep-linking docs (`android_deep_links.md`).

**Tests**: `backend_test.py` + `pytest.ini` (xdist `-n 2 --dist loadscope`).
Do not change the pytest `addopts`. Run `pytest` from `backend/`.

---

## Known gaps / NOT implemented (do not assume otherwise)

| Area | Gap | Impact | Likely fix |
|---|---|---|---|
| Vector index | No tuned HNSW/IVFFlat index; plain pgvector `<=>` search | Slow at large corpus | Add HNSW index after bulk ingest |
| Retrieval | Hybrid (dense + BM25 + RRF) built; no tuned BM25/vector params tuned to the corpus, no top-k slider | Quality/param tuning | Calibrate `DENSE_K`/`LEXICAL_K`/`RRF_K`, optional top-k slider in UI |
| Streaming | Chat response is non-streamed | UX | SSE/websocket on `/ask` |
| Rate limiting | No per-user/NIM request quotas | Cost runaway | Token-bucket limiter on `/api/chat/*` |
| Admin audit log | `allowed_roles` edits are not logged | No compliance trail | `document_audit_log` table |
| Multi-document chat | One doc query scope only | Cross-doc answers tagged weird | Enable cross-doc mode + `allow_any` param |
| Conversation UX | No rename/delete/export in the chat UI | — | Simple endpoints + UI |

---

## Roadmap (next)

1. **stability first**: add HNSW index, rate limiting, and audit logging on admin
   role edits.
2. **retrieve smarter**: calibrate fusion params (`DENSE_K`/`LEXICAL_K`/`RRF_K`) on
   real data and add an optional top-k slider; consider HNSW for larger corpora.
3. **streaming answers** and chunk-level citations-to-source links in the UI.
4. **Admin polish**: pagination for large docs, per-document role → chunk
   bulk (the "apply doc roles to all chunks" convenience), and CSV user export.
5. **Android hardening** follows the Capacitor build.

---

## Source of truth

- Canonical README / docs: `README.md` → `design_guidelines.md` → `DEPLOY_HF_SUPABASE.md`.
- Historical notes void read: `archive/plan.md`, `archive/audit_findings.md`.
- If this doc and the code ever disagree, the code wins — open an issue.
