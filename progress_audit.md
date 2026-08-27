# RBAC Hybrid RAG — Progress Audit (Code-Grounded)

**Method:** every file in `backend/`, `frontend/`, `migrations/`, `scripts/` was read directly. Claims in `PROJECT_STATUS.md`, `README.md`, and `archive/` were **not** used as evidence — findings below are what the code actually does.

**Verdict:** this is a genuinely more mature build than most first-pass RAG projects — the core RBAC-in-SQL principle (production spec §4) is implemented correctly, and role-revocation is checked fresh on every request. But it is a **single-tenant, role-only** system with no vector index, no audit trail, no object storage, and no pipeline durability. It's a solid POC/MVP, not yet production per our spec.

---

## 1. What's actually solid (verified in code)

| Capability | Where | Notes |
|---|---|---|
| **ACL filtering happens inside the SQL `WHERE` clause on both legs** | `retrieval.py` `_dense_retrieve`, `_lexical_retrieve` | Matches spec §4 exactly — `WHERE d.status='published' AND c.allowed_roles && :r`, not a post-filter. This is the single most important correctness property and it's done right. |
| **Defense-in-depth app-level re-check** | `retrieval.assert_rbac()`, called in `chat_router.py` after fusion | Raises loudly if an unauthorized chunk ever reaches memory. Good belt-and-suspenders, though it's an app assertion, not DB-enforced (see gaps). |
| **Fresh authorization on every request (no stale-allow window)** | `deps.py get_current_user` | Role/status is re-queried from `profiles` on every call — a revoked/demoted user is denied on their very next request. This satisfies spec §8's hardest requirement (revocation) by construction. |
| **Chunk-level ACL ceiling enforcement** | `admin_router.py update_chunk_roles` | A chunk's roles can't exceed its parent document's roles — prevents privilege drift during manual review. |
| **Human-in-the-loop ACL tagging** | `nim_client.suggest_chunk_roles`, `pending_review`→`published` workflow | AI suggests per-chunk roles at ingestion; nothing is queryable until an admin explicitly publishes. Not in the original spec, but a genuinely good safety addition. |
| **RRF fusion + real cross-encoder reranking** | `retrieval._rrf_fuse`, `reranker.py`, NIM reranker | Implemented correctly, with score parsing hardened against API response drift, and safe RRF-order fallback if the reranker call fails. |
| **JWT verification is solid** | `auth.py` | Delegates to Supabase JWKS, pins `ES256` explicitly (no algorithm-confusion risk), checks `audience`. |
| **Partial prompt-injection defense (citation forgery)** | `chat_router._generate_answer` system prompt | Explicitly instructs the model that filenames appearing *inside* chunk text are not real sources — blocks a specific, realistic injection (fake "further reading" citations). |
| **Document-summary path re-authorizes independently** | `retrieval.resolve_document_by_id`, `document_chunks` | Well-tested (see `test_document_summary.py`) against cross-role leakage, similar-filename confusion, and revoked access. |

---

## 2. Gap-by-gap vs. the production spec

### §2 — Multi-tenancy: **not implemented**
There is no `tenant_id` anywhere in the schema (`database.py`). This is a single-organization system. Fine if that's the actual product goal, but if "production" means multi-customer SaaS, this is a foundational gap — retrofitting tenant isolation after data exists is much harder than building it in.

### §4 — ACL as a query predicate: **implemented** ✅
Covered above. This is the one gap from the original review that's fully closed.

### §5 — Postgres RLS as defense-in-depth: **implemented in name only**
`migrations/001_supabase_auth.sql` enables RLS on all tables but adds **zero policies**. The comment in the migration is honest about this: *"RLS enabled with ZERO policies = default-deny for the frontend's anon key... the backend connects with the service-role/owner string, which bypasses RLS."* So RLS currently only stops a browser from querying Supabase directly with the anon key — it does **nothing** to protect against an application-layer bug in the backend, which is the actual threat model §5 is meant to cover. There's no `SET LOCAL app.current_principals` anywhere, no per-role policy.

### §6 — Filtered ANN indexing: **not implemented**
`grep` across the whole repo for `HNSW`/`IVFFlat`/`vector_cosine_ops` returns nothing. The only indexes are a GIN on `allowed_roles` and a btree on `document_id`. Every similarity search (`embedding <=> :q`) is a **full sequential scan** of the `chunks` table. This won't show up as a bug at demo scale (dozens–hundreds of chunks) but will degrade sharply as the corpus grows — and it means the "filtered-ANN correctness" problem from §6 hasn't been reached yet because there's no ANN index to filter around at all.

### §7 — Pipeline idempotency/rollback: **not implemented**
`admin_router._persist_document` does one `INSERT` for the document and a loop of `INSERT`s for chunks, all before a single `db.commit()`. There's no `pipeline_run_id`, no atomic swap-in step, and — more importantly — **no object storage for the original file at all**. Only extracted/chunked text is persisted; the source PDF/DOCX is read into memory and discarded. That means: no re-parsing if the chunking strategy changes, no audit copy of what was actually uploaded, and if embedding fails mid-loop the transaction likely rolls back cleanly (SQLAlchemy default), but there's no formal `FAILED` status path or retry semantics — it's just an unhandled exception surfaced as a 500/502 to the admin.

### §8 — Cache invalidation consistency: **partially moot, partially unaddressed**
There's no caching layer at all (no Redis, no in-memory TTL cache), so there's nothing to invalidate — which incidentally means the *revocation* half of §8 is satisfied by having no cache (see §1 above). But this also means there's no performance caching anywhere, and document ACL changes propagate immediately only because every query re-reads current state directly — fine at current scale, but worth knowing this isn't a deliberate consistency design, it's an absence of a cache layer.

### §9 — Prompt injection defense: **partially implemented**
The system prompt in `chat_router._generate_answer` blocks one specific injection vector (fake citations from names mentioned inside chunk text) but there's no general defense against an uploaded document containing an embedded instruction like *"ignore previous instructions."* There's no structural delimiting (e.g., XML-tagged untrusted-data blocks), no input-side sanitization at ingestion (`ingest.py` does whitespace/control-char cleanup only, not injection-pattern screening), and no output-side groundedness check — the "validate answer and citations" step from the original flow is aspirational in the prompt text, not verified after the fact.

### §10 — Encryption / secrets / rate limiting: **encryption and secrets are reasonable for this stage; rate limiting is missing**
- `.env.example` files contain placeholders only, no real secrets committed — good hygiene.
- TLS is handled by Supabase/hosting automatically; no custom encryption-at-rest logic needed since there's no self-managed storage.
- **No application-level rate limiting** anywhere in `requirements.txt` or `server.py` (no `slowapi`, no per-user/per-tenant throttle). The only rate-limit handling is *reactive* — catching NIM's own 429s in `nim_client.py`. A single user could currently hammer `/chat/ask` with no backend-side throttle.
- No KMS/secrets-manager integration — acceptable for a Hugging Face Spaces / Vercel deployment at this stage, but noted as a gap if this moves to a regulated or enterprise deployment.

### §11 — Re-embedding strategy: **not implemented**
`embedding vector(1024)` is a fixed column with no `embedding_model_version` field. Changing `NIM_EMBED_MODEL` today would silently mix incompatible embeddings in the same similarity search with no versioning to detect it.

### Audit logging (design flow step "write audit logs"): **not implemented**
There is no `audit_log` table and no immutable security event trail. `messages.retrieval_detail` (jsonb) records retrieval transparency for the *chat UI* (which chunks were used/blocked, scores) — useful, but it's a UX feature, not a tamper-evident audit log, and it doesn't cover admin actions (uploads, role changes, publishes, deletes) at all.

### Document update/versioning flow (original design §9): **not implemented**
There's no `version` column, no "new version detected → re-parse → replace old chunks" flow. `PATCH /documents/{id}` only edits role tags; there's no re-upload/reprocess path. Deletion is a hard `DELETE ... CASCADE` — no `DELETING` transitional status, no soft delete, no archival step, and (per above) no original file to archive anyway.

### Malware scanning (original design flow step 1): **not implemented**
`admin_router._validate_size` / `_validate_filename` check file size and extension only. No malware/antivirus scan, no file-hash-based dedup.

---

## 3. Where this actually sits

Treat it as roughly **60–65% of the way to the spec** — but weighted toward the *hardest and most security-critical* piece (in-SQL ACL filtering, fresh revocation checks) being done right, and the *infrastructure-hardening* pieces (RLS-with-policies, vector indexing, audit trail, pipeline durability, tenancy, malware scanning) being the part still ahead of you. That's actually the better order to have solved things in — but it means the remaining work is mostly infra/ops, not RAG logic.

## 4. Suggested priority order for next work

1. **Add a vector index** (`CREATE INDEX ... USING hnsw`) — highest ratio of production-risk-reduced to effort. Currently every query is a sequential scan.
2. **Write real RLS policies** using `SET LOCAL` session variables, so the backend itself is protected by a second, independent layer — not just the anon key.
3. **Add an `audit_log` table** and write to it from every admin action + every `/chat/ask` call (who, what role, which chunks, blocked count). This is usually the first thing a security review asks for.
4. **Add basic rate limiting** (`slowapi` is a one-afternoon addition) on `/chat/ask` and `/admin/documents`.
5. **Decide the tenancy question explicitly** even if the answer is "single-tenant is fine for now" — write that decision down so it isn't accidentally assumed later.
6. **Object storage for original files** — needed before any re-chunking/re-embedding strategy is possible, and for basic audit completeness.
