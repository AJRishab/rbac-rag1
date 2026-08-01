# plan.md — Sentry RAG (Permission-aware RAG) — UPDATED (v1 COMPLETE)

## 1) Objectives
- Confirm the **core workflow** works end-to-end with real services (no mocks):
  - **NVIDIA NIM** embeddings + chat
  - **PostgreSQL + pgvector** vector retrieval
  - **RBAC filtering inside SQL** so disallowed chunks never leave the DB
- Deliver a full-stack MVP (FastAPI + React) with:
  - Auth (register → pending → admin approval → login)
  - Admin console (user approvals + document upload + role tagging)
  - Chat (citations, persisted conversation history, and **persisted retrieval details**)
- Ensure and verify: **same question + different roles ⇒ different retrieved chunks/answers**, including evidence via retrieval details.
- Current objective (post-v1): **stabilize, document, and prepare for iterative enhancements** (performance, UX, and hardening) without changing the v1 behavior.

---

## 2) Implementation Steps

### Phase 1 — Core POC (isolation; do not proceed until passing) ✅ COMPLETED
**Goal:** validate NIM + pgvector + RBAC-filtered retrieval + RAG generation.

1. **Infra bring-up (local)** ✅
   - Installed **PostgreSQL 15** and enabled `pgvector` (**built from source**, version **0.7.4**).
   - DB: `sentry_rag` on port `5432`.
   - Postgres managed via **supervisor**.

2. **POC script (`poc_rbac_rag.py`)** ✅
   - Called NIM embeddings (`nvidia/nv-embedqa-e5-v5`) and verified **1024-dim** vectors.
   - Stored embeddings in Postgres pgvector.
   - Retrieval query enforced RBAC **inside SQL**:
     - Role-filtered: `WHERE allowed_roles && ARRAY[user_role]`
     - Admin bypass: retrieval across all chunks
   - Ranked by pgvector cosine distance.
   - Sent **only retrieved chunks** to NIM chat model; generated answer + citations.

3. **POC verification tests (assertions/output)** ✅
   - Same query as `employee` vs `hr` returned different chunk IDs.
   - Admin returned the union / full set.
   - Output included `retrieved_count` and computed `blocked_count`.

**Exit criteria:** POC script runs cleanly and demonstrates RBAC-differentiated retrieval + RAG answer. ✅

---

### Phase 2 — V1 App Development (real backend + real frontend, minimal but complete) ✅ COMPLETED
**Goal:** full working product around the proven core.

#### 2.1 Backend (FastAPI + async SQLAlchemy + asyncpg) ✅
- **Schema init on startup (idempotent)**
  - `users`, `documents`, `chunks` (pgvector 1024), `conversations`, `messages`
  - Extensions: `vector`, `pgcrypto`
- **Admin seed/bootstrap**
  - Seed default admin on startup:
    - Use `ADMIN_EMAIL`/`ADMIN_PASSWORD` if provided
    - Else auto-generate a password, set `must_change_password=true`, and log credentials
- **Auth + gating**
  - Register → `pending`, no role
  - Login returns JWT; app routes based on `status` + `must_change_password`
  - Protected endpoints enforce approved+role; admin endpoints enforce admin role
- **Admin endpoints**
  - List users, approve pending users + assign role, change roles
  - Upload/list/edit/delete documents
  - Upload supports: `.txt`, `.md`, `.pdf`, `.docx`
- **Chat endpoints**
  - Conversations: list, delete
  - Messages: list per conversation
  - RAG: `POST /api/chat/ask`
    - Embed question (NIM)
    - Retrieve top-k with RBAC **inside SQL**: `WHERE c.allowed_roles && ARRAY[user_role]`
    - Compute blocked chunk details (what would have been retrieved without filter)
    - Generate answer using NIM chat model, return **citations + retrieval detail**, persist them to `messages`
- **NIM wrapper**
  - Retry/backoff and clear handling for 429/timeout

#### 2.2 Ingestion pipeline ✅
- Parse files into text:
  - TXT/MD (decode)
  - PDF (`pypdf`)
  - DOCX (`python-docx`)
- Chunking:
  - Token-based chunking using `tiktoken` (`cl100k_base`)
  - ~500 tokens with 50-token overlap
- Embeddings:
  - Model: `nvidia/nv-embedqa-e5-v5` (`input_type=passage` / `query`)
  - Stored in `chunks.embedding vector(1024)`

#### 2.3 Frontend (React + Tailwind + shadcn/ui; dark control-room aesthetic) ✅
- **Landing**: dark-only control-room design with grid + radar rings, hero + 4 feature panels + final CTA
- **Auth flows**: Login / Register / Pending Approval / Change Password (forced)
- **Chat UI**:
  - Sidebar with conversation history + new conversation
  - Persistent user email + role badge
  - Answer cards include:
    - Citation chips
    - Collapsible **Retrieval Details** panel (retrieved vs blocked, distances, admin bypass note)
  - Fully wired to backend; no mocked responses
- **Admin console**:
  - Users tab: approve pending users + role assignment
  - Documents tab: upload dropzone, role checkboxes, doc list, edit roles dialog, delete
- **Routing protections**:
  - Non-admin cannot access `/admin` even via URL; redirects to `/chat`

#### 2.4 Phase 2 testing ✅
- regression test results:
  - **Backend**: 100% (15/15)
  - **Frontend**: 95% (18/19)
  - Only noted issue: “JWT expiry during extended automated runs” (expected; tokens are time-bound)

**Exit criteria:** end-to-end app works with real DB + NIM, and RBAC-differentiated answers are reproducible. ✅

---

### Phase 3 — Hardening + UX polish (still MVP scope) ⏭️ NEXT (OPTIONAL / POST-v1)
**Goal:** improve robustness, performance, and operator trust without changing core RBAC behavior.

1. **RBAC/audit correctness**
   - Add explicit regression test that verifies RBAC filter is applied in SQL (server-side test against query plan or a known RBAC fixture).
   - Ensure retrieval details remain persisted and shown after conversation reload (already implemented; keep under regression).

2. **Performance/quality**
   - Add pgvector ANN index strategy:
     - Evaluate `ivfflat` or `hnsw` index depending on pgvector build/config
     - Run `EXPLAIN ANALYZE` sanity check
   - Optional: embedding caching for repeated uploads/queries.

3. **Error handling / reliability**
   - Improve NIM 429 handling UX:
     - UI shows friendly toast (already) + optional “retry” button
   - Upload parsing improvements:
     - Better PDF extraction fallback
     - Clearer parse failure diagnostics

4. **UX improvements (future)**
   - Streaming responses (server-sent events / websockets)
   - Better citation formatting (doc section anchors)
   - Chunk-level role tagging UI (schema supports it; `allowed_roles` is on `chunks`)

**Phase 3 exit criteria:** regression suite covers RBAC differentiation + history persistence; performance acceptable; errors are user-friendly.

---

## 3) Next Actions (immediate)
- **Ready for exploration**: use provided credentials and existing documents to demo RBAC behavior.
- Optional follow-ups:
  1. Add streaming responses.
  2. Add chunk-level tagging UI.
  3. Add ANN indexing + performance tuning.
  4. Add multi-tenant/org support.

---

## 4) Success Criteria
### Proven (v1) ✅
- **POC**: same query yields different retrieved chunk IDs for different roles; admin sees all; NIM returns answer with citations.
- **App**: no mocks; users can register/pending/approved/login; admin can approve + upload/tag docs; chat answers include citations + persisted retrieval detail.
- **Security**: disallowed content is never sent to the LLM; retrieval filtering occurs inside SQL.
- **Reliability**: NIM 429/timeout handled gracefully; conversations persist and reload correctly.

### Future (Phase 3+) ⏭️
- Higher-scale retrieval performance via ANN indexes.
- Improved UX (streaming, richer citations, better upload diagnostics).
- Advanced ranking (hybrid search, reranking) and multi-tenant support.