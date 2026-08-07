> **ARCHIVED.** Historical hygiene-audit snapshot (findings have since been
> addressed in code). Current status lives in `../../PROJECT_STATUS.md`.

# Sentry RAG — Codebase Audit Findings

Scope: `RBAC-RAG/backend/` and `RBAC-RAG/frontend/src/`. Skipped `node_modules/`,
`venv/`, `build/`, and `components/ui/` (generated shadcn primitives).

Audit type: **hygiene pass** — findings only, no edits applied in this pass.

Risk legend:
- `cosmetic` — no functional impact
- `could cause a bug` — may break/config-misalign under some conditions
- `security-relevant` — should be addressed before production

---

## 1. Auth-migration leftovers (priority)

| # | File:line | Description | Suggested fix | Risk |
|---|-----------|-------------|---------------|------|
| 1.1 | `backend/server.py:6-7` | Module docstring still lists `JWT_SECRET` and `ADMIN_EMAIL/ADMIN_PASSWORD` as the env contract — neither exists anymore. | Refresh the docstring to the Supabase env vars (`SUPABASE_URL`, `SUPABASE_JWT_SECRET`, `DATABASE_URL`, `NIM_API_KEY`, `CORS_ORIGINS`). | cosmetic |
| 1.2 | `backend/auth.py:5,17` | Token verification switched to **JWKS/ES256 via `SUPABASE_URL`** — but `DEPLOY_HF_SUPABASE.md:101` instructs setting `SUPABASE_JWT_SECRET`, which **no code reads**. Also `auth.py:5` = `os.environ["SUPABASE_URL"]` at import → `KeyError` crash if unset. | Pick one: keep JWKS + document `SUPABASE_URL` as required, **or** revert to HS256 using `SUPABASE_JWT_SECRET`. Align env vars in code + deploy doc. | could cause a bug |
| 1.3 | `backend/database.py:38-46,52,80` | `SCHEMA_SQL` still creates the deprecated **`users` table** and FKs `documents.uploaded_by` / `conversations.user_id` against it. (001 migration drops those FKs afterwards, so it works, but the dead table/`password_hash` column is re-created every startup.) | Remove `users` table + both `REFERENCES users(id)` clauses from `SCHEMA_SQL` (profiles is identity now). | cosmetic |
| 1.4 | `backend_test.py:305-308` | Test harness hardcodes account emails/passwords (`admin@sentry.local` / `Admin@2026`, etc.) — couples the test to one Supabase tenant's data. | Parameterize via env (`TEST_ADMIN_EMAIL`/`TEST_ADMIN_PASSWORD`). | cosmetic |
| 1.5 | — | `hash_password`, `verify_password`, `create_access_token`, `decode_token`, `sentry_token`: **no references found** across all 129 files. `/auth/register`/`/auth/login` not defined (`auth_router.py` has only `/me` + `/change-password`) and not called by the frontend. `backend_test.py` authenticates via Supabase REST (`/auth/v1/token`, `/auth/v1/signup`), not removed endpoints. | No action — cleanup confirmed complete. | n/a |

---

## 2. Dead / unused code

| # | File:line | Description | Suggested fix | Risk |
|---|-----------|-------------|---------------|------|
| 2.1 | `frontend/src/constants/testIds/home.js` | Exports `HOME`; `index.js` only re-exports `./sentry`, and no file imports `./home` or uses `HOME.` — dead. | Delete `home.js` (requires approval). | cosmetic |
| 2.2 | `frontend/src/constants/testIds/auth.js` | `LOGIN`/`REGISTER`/`LOGOUT` templates are dead — not re-exported and never imported (app uses `AUTH` from `sentry.js`). | Delete `auth.js` or re-export if templates are wanted (approval). | cosmetic |
| 2.3 | `backend/poc_rbac_rag.py` | Phase-1 standalone POC (own `poc_chunks` table, own NIM/DATABASE reads). Functional and proves RBAC, superseded by `backend_test.py`. | **Decision point** — keep as reference, or move to `examples/`/archive. Don't silently delete. | cosmetic |
| 2.4 | `frontend/src/constants/testIds/sentry.js:23-26` | `AUTH.changePasswordCurrent...` keys may be unused now that change-password dropped the "current password" field. | Verify usage; trim if unused. | cosmetic |

---

## 3. Security / secrets hygiene

| # | File:line | Description | Suggested fix | Risk |
|---|-----------|-------------|---------------|------|
| 3.1 | `backend/server.py:69` | `allow_origins=os.environ.get("CORS_ORIGINS", "*")` defaults to wildcard `*`, combined with `allow_credentials=True` (line 68). Any deploy missing `CORS_ORIGINS` runs with `*` + credentials. | Require `CORS_ORIGINS` explicitly in production (no `*` fallback, or reject `*` when credentials are on). | security-relevant |
| 3.2 | git history | `backend/.env` + `frontend/.env` are **gitignored** (`git check-ignore` confirms) and **never committed** (`git log --all -- '**/*.env'` + `git ls-files` show nothing tracked). | No credential rotation needed — leave as-is. | n/a (confirmed clean) |
| 3.3 | — | Hardcoded secrets in source: **none** outside `.env` (only test creds in 1.4). | n/a | n/a |
| 3.4 | Supabase dashboard | RLS on `profiles`/`documents`/`chunks`/`conversations`/`messages` — declared in `migrations/001_supabase_auth.sql` but **must be manually verified in the dashboard**; cannot be confirmed from source. | Manual check: RLS enabled + zero extra policies on all five tables. | security-relevant (manual check) |

---

## 4. General code quality

| # | File:line | Description | Suggested fix | Risk |
|---|-----------|-------------|---------------|------|
| 4.1 | `frontend/src/lib/api.js:14-18,37-46,59-61,67-72` | Leftover debug `console.log`/`console.error` dumps (URL/session/request). | Remove or gate behind `NODE_ENV !== 'production'`. | cosmetic |
| 4.2 | `frontend/src/lib/supabaseClient.js:6-12` | Debug `console.log` printing `SUPABASE_URL`/anon-key presence. | Remove or gate. | cosmetic |
| 4.3 | `backend/admin_router.py:77` + `backend/chat_router.py:22` | `_fmt_vec` defined **identically in two routers** (duplicated logic). | Move to a shared helper and import in both. | cosmetic |
| 4.4 | `backend/routers/auth_router.py:18-29` | `/me` re-queries `profiles` though `deps.get_current_user` already fetched the same row — duplicate DB hit. | Return the row from the dependency instead of re-querying. | cosmetic |
| 4.5 | `.emergent/emergent_todos.json` | **File/dir no longer exists** (`.emergent` removed in earlier cleanup); the `in_progress` entry is gone entirely. | No action. | n/a |
| 4.6 | Router auth coverage | All admin routes → `require_admin`; chat/conversations → `require_approved`; `/me` + `/change-password` → `get_current_user`. **No endpoint missing required protection.** | No action. | n/a |

---

## Guardrails (do NOT touch without explicit approval)

- `chat_router.py` retrieval logic (`_retrieve_role_filtered`, `_retrieve_admin`, the `allowed_roles &&` SQL filter) — core RBAC, out of scope.
- `ingest.py` chunking/embedding logic, and `nim_client.py` `suggest_chunk_roles` batching.
- No file deletion unless it appears in this list and is explicitly approved.

*This document is the audit snapshot; nothing has been edited as part of producing it.*


