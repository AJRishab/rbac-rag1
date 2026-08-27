# RBAC Hybrid RAG — Progress Audit (Code-Grounded)

**Last verified:** 2026-08-27 (fresh full pass — this file was rewritten from source, not carried over).

**Method:** every runtime file in `backend/` and `backend/routers/`, the SQL migration(s), `frontend/src` routing/auth, and `requirements.txt` were read directly in this pass. Claims are tied to file:line below. `PROJECT_STATUS.md` / `archive/` were **not** used as evidence. This audit measures the **gap between the production spec (`goal.md`) and the current codebase**.

**Deployed topology (confirmed):** Vercel frontend (`rbac-rag-nine.vercel.app`) · Render backend (`rbac-rag1.onrender.com`) · Supabase Postgres+Auth · NVIDIA NIM for embeddings/chat/rerank.

---

## 1. Verified solid — actually implemented in code

| Capability | Evidence | vs. spec |
|---|---|---|
| **ACL is a query predicate, not a post-filter** — dense AND BM25 both carry `WHERE d.status='published' AND c.allowed_roles && :r` inside SQL. | `backend/retrieval.py` `_dense_retrieve`, `_lexical_retrieve`; called from `hybrid_retrieve`. | ✅ §4 fully met |
| **Chunk-level ACL ceiling** — a chunk's `allowed_roles` can never exceed its parent document's roles. | `backend/routers/admin_router.py` `update_chunk_roles`. | ✅ extra safety |
| **Nothing retrievable until published** — only `status='published'` docs are in the WHERE predicate; no post-filter. | `retrieval.py` + `pending_review→published` in `admin_router.py` `publish`. | ✅ spec §3 |
| **Fresh authorization per request** — `profiles` re-queried on every call, so revocation/demotion takes effect next request. | `backend/deps.py` `get_current_user`. | ✅ spec §8 (revocation half) |
| **Defense-in-depth app re-check** post-fusion (raises loudly if unauthorized chunk reaches memory). | `retrieval.assert_rbac`, called in `chat_router.ask`. | ✅ (app layer only — DB RLS still missing, see §2) |
| **RRF fusion + cross-encoder rerank** with safe RRF-order fallback on reranker failure. | `retrieval._rrf_fuse`; `reranker.py`. | ✅ §4/§12 pipeline |
| **JWT verification** via Supabase JWKS, ES256 pinned, audience checked. | `backend/auth.py`. | ✅ §10 (auth) |
| **Partial prompt-injection defense** — dedicated `DEFENSE-IN-DEPTH SOURCE RULES` in the system prompt (block fabricated "documents"/fake far sources). | `chat_router._generate_answer`. | ⚠️ partial §9 |
| **Document-summary path re-authorizes independently** + dedicated RBAC-leak tests. | `retrieval.document_chunks` (RBAC in SQL); `backend/test_document_summary.py`. | ✅ §4 |
| **Idempotent schema bootstrap + Supabase Auth migration applied at startup; identity off legacy `users`.** | `backend/database.py init_db`; `migrations/001_supabase_auth.sql`; legacy `users` table no longer created. | ✅ §10 hygiene (partial) |
| **Secrets hygiene** — `.env` gitignored; `.env.example` contains placeholders only. | `.gitignore`, `backend/.env.example`, `frontend/.env.example`. | ✅ §10 |


---

## 2. Gap-by-gap vs. the production spec (`goal.md`)

### §2 — Multi-tenancy: **NOT implemented**
No `tenant_id` in any table (`database.py` SCHEMA: documents/chunks/conversations/messages have none). Single-organization only. If the product is multi-customer SaaS this is a foundational, hard-to-retrofit gap.

### §4 — ACL as a query predicate: **implemented** ✅ (see §1)
The single most important correctness fix is done correctly.

### §5 — Postgres RLS as defense-in-depth: **enabled in name only**
`001_supabase_auth.sql` enables RLS on all 5 tables but adds **zero policies** and there is **no `SET LOCAL app.current_*`** anywhere. The backend connects with the service-role/owner string, which bypasses RLS — so RLS currently only stops a browser from querying Supabase directly with the anon key. It does **not** protect the backend against its own application-layer bug, which is exactly the §5 threat model. **This is the biggest security gap.**

### §6 — Filtered-ANN index: **RESOLVED this session (tracked `005` migration)**
A tracked migration now rebuilds the similarity index. `database.py` was changed to apply **all** `migrations/*.sql` in order at startup, and a new `005_openrouter_embed_1024.sql` re-creates `chunks_embedding_hnsw_idx` (`(embedding) vector_cosine_ops`, 1024-dim) in the same pass that converts the embedding column to 1024. `retrieval.py` still sets `hnsw.ef_search` as a query-time tuning knob. Remaining task: verify with `EXPLAIN ANALYZE` under the ACL predicate on a populated corpus.

### §7 — Pipeline idempotency / rollback / object storage: **NOT implemented**
- `_persist_document` inserts the doc + all chunks in one transaction (no `pipeline_run_id`, no staging swap, no `FAILED` status path — only `pending_review`/`published`).
- **No object storage for original files** — `upload_document` reads the file into memory (`admin_router.py`), and only chunked text + embeddings are persisted. No re-parsing capability, no audit copy of the upload, no source file ever retained.

### §8 — Cache/invalidation consistency: **partially moot**
There is no cache layer, so the revocation guarantee holds by construction (fresh read each request). But there's also no performance caching and no write-through invalidation design. Acceptable at current scale; not a deliberate design.

### §9 — Prompt-injection defense: **partially implemented**
Solid **source-identity** blocks (see §1) but **no** ingestion-time injection sanitation (`ingest.py` only strips whitespace/control chars), **no** structural delimiting (e.g., XML-tagged untrusted-data blocks), and **no output-side groundedness check** — the "answer only from sources" rule lives in the prompt text, not verified after generation.

### §10 — Encryption / secrets / rate limiting: **secrets good, rate limiting MISSING**
- Encryption: TLS handled by Supabase/Render; no custom KMS; acceptable at this stage.
- Secrets: `.env.example` placeholders only — ✅.
- **No application-level rate limiting** anywhere (`requirements.txt` has no limiter; no `slowapi`). The only 429 handling is *reactive* inside `nim_client.py` (retrying NIM's own rate-limit responses). Any authenticated user can hammer `/chat/ask` and `/admin` with no per-user/per-tenant throttle, and there's no per-user cost control on the expensive LLM/rerank calls. **NOT met (§10).**


### §11 — Re-embedding & embedding versioning: **partially addressed (dimension) / still no versioning**
- The embedding model is now **OpenRouter `qwen/qwen3-embedding-0.6b` @ 1024-dim** (`database.py` SCHEMA `vector(1024)`), with a tracked `005` migration + `scripts/reembed_openrouter.py` to convert/re-embed. `nim_client.py` was replaced by `openrouter.py` (embeddings + chat + rerank all on OpenRouter).
- **Still `NOT implemented`:** an `embedding_model_version` column and a dual-write migration path — a future embedding-model change can still silently mix incompatible vectors.

### Audit logging: **NOT implemented**
No `audit_log` table. `messages.retrieval_detail` (jsonb) is a UI-transparency feature (chunks used/blocked per chat reply) — useful, but not a tamper-evident admin/security trail. Admin actions — uploads, role changes, publishes, deletes — are **not logged at all**.

### Document versioning / update: **NOT implemented**
No `version` column, no re-upload/reprocess path; `PATCH /admin/documents` only edits role tags; delete is a hard `DELETE CASCADE`.

### Malware scanning / dedup: **NOT implemented**
`_validate_size` / `_validate_filename` (size + extension only, `admin_router.py`). No malware scan, no content-hash dedup.

### Frontend quick-read
Auth gating is solid and role/status-aware (`ProtectedRoute`, `AuthContext` re-fetches `/auth/me`, 401-expiry handling in `lib/api.js`). Chat UI threads real retrieval detail into every bubble. The gaps are **backend/infra**, not UI.

---

## 3. Where the project sits

- **Done / strong (~40%):** in-query ACL (the core correctness property), adversarial document-source rules, fresh revocation, chunk role ceilings, human-in-loop publish gate, hybrid search + rerank, document-summary RBAC tests.
- **Missing (the remaining ~60%):** multi-tenancy, real RLS policies (backend-facing), a tracked HNSW index migration (regressed this session), audit log, pipeline idempotency + object storage, app-level rate limiting, versioned re-embedding/update path, malware scanning.

The hardest, most security-important slice (in-SQL ACL, revocation) is correct; what's left is mostly **infra/ops hardening** — except the two *security-critical* items (#1 and #2 below).

## 4. Recommended order for next work

1. **Re-introduce a tracked RLS policy layer** — session variables for backend role resolution AND actual RBAC policies, so the DB defends the backend itself (covers §5).
2. **Tracked vector index migration** — a repo-reproducible HNSW migration using `(embedding::halfvec(2048))` matching the current `vector(2048)` schema; verify with `EXPLAIN ANALYZE` that filtered retrieval uses the index (closes the regression introduced this session).
3. **App-level rate limiting** on `/chat/ask` + `/admin` — a one-afternoon change that closes the cost-blowout risk.
4. **Audit log table** + write on every admin mutation and every `/ask` (actor, role, chunks served, blocked count).
5. **Decide tenancy explicitly** (even "single-tenant by design") and write it down — no accidental `tenant_id` assumptions later.
6. **Object storage for original files** — prerequisite for re-chunking, re-embedding (§7/§11), and audit completeness.

> **Deployment note:** the repo now targets OpenRouter + `vector(1024)`. The **live Supabase DB** is still on `vector(2048)` with Nemotron embeddings and the old `halfvec(2048)` HNSW index. On next deploy, `005_openrouter_embed_1024.sql` will convert the column, NULL old embeddings, and rebuild the index — **you must then run `scripts/reembed_openrouter.py`** (with `OPENROUTER_API_KEY` set) to repopulate embeddings before retrieval returns results. Until that re-embed runs, similarity search returns only BM25-lexical results (dense leg yields nothing).
