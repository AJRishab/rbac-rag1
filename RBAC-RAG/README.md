---
title: Sentry RAG
emoji: 🛡️
colorFrom: slate
colorTo: blue
sdk: docker
pinned: false
app_port: 7860
---

# Sentry RAG

Permission-aware RAG: **FastAPI + React + PostgreSQL/pgvector + NVIDIA NIM**.

Documents are chunked, embedded, and tagged with the roles allowed to see them.
When a user asks a question, retrieval is filtered by that user's role **inside the
SQL query**, so restricted content is never even touched by the answer step.

## Highlights

- **RBAC enforced at retrieval time** — the role filter is a `WHERE` clause on a cosine
  similarity query; the LLM only ever sees chunks the user is allowed to read.
- **Chunk-level role tagging** — the NIM LLM suggests roles per chunk during upload;
  an admin reviews, adjusts, and publishes. Unpublished documents are never retrievable.
- **Transparent retrieval** — every answer records how many chunks were retrieved vs.
  blocked by access rules, with per-answer `retrieval_detail` persisted.
- **Supabase-flavored auth** — signup/login via Supabase Auth (JWT), profile records in
  the `profiles` table, admin-managed approval + role assignment.
- **NVIDIA NIM** — `nvidia/nemotron-3-embed-1b` embeddings (2048 dimensions) and a NIM chat model; retries and
  HTTP 429 handling built in.
- **Deployable free** — a Docker Space serves the React SPA and the API on one port
  (`7860`); an optional Vercel frontend and Capacitor Android build are supported.

## Architecture

```
Supabase (auth + Postgres/pgvector)          NVIDIA NIM (embeddings + chat)
        │  JWT (verified via JWKS)                    │
        └─────────────── FastAPI  ◄──────► npm (React SPA)
                             │
             ┌───────────────┴───────────────┐
        /api/auth  ·  /api/admin  ·  /api/chat
```

Three routers:

| Router | Base path | Responsibility |
|--------|-----------|----------------|
| `auth_router` | `/api/auth` | Current-user + change-password |
| `admin_router` | `/api/admin` | User approval/roles, document lifecycle |
| `chat_router` | `/api/chat` | Conversations, messages, RBAC-gated RAG ask |

## Repo layout

```
RBAC-RAG/
├─ Dockerfile                 # Runtime for the Hugging Face Space (React build + API)
├─ backend/
│  ├─ server.py              # FastAPI app, /api, CORS, SPA serving
│  ├─ database.py            # init_db, tables, handle_new_user trigger
│  ├─ deps.py                # require_approved / current-user deps (JWT via JWKS)
│  ├─ nim_client.py          # NIM embeddings + chat + chunk-role suggestion
│  ├─ ingest.py              # parsing → chunking (~500-token, 50 overlap) → embedding
│  ├─ schemas.py             # Pydantic request/response models
│  ├─ routers/               # auth_router, admin_router, chat_router
│  ├─ migrations/            # SQL migrations
│  ├─ examples/              # sample uploads / requests
│  └─ backend_test.py        # backend test suite (see "Tests")
├─ frontend/
│  └─ src/                   # React (CRA + craco, Tailwind, shadcn/ui, Supabase, Capacitor)
└─ *.md                      # docs (see "Docs index" below)
```

## How RBAC is enforced

1. **Upload** (`POST /api/admin/documents`) — the file is parsed, chunked, embedded, and
   the NIM model suggests `allowed_roles` per chunk (`roles_ai_suggested = true`).
2. **Review** — admins browse chunks, correct the suggested roles, then publish the
   document (`POST /publish`). Only `status = 'published'` documents are searchable.
3. **Ask** — the query is embedded, then one SQL statement ranks chunks by cosine
   distance while keeping only chunks whose `allowed_roles` overlap the caller's role:

   ```sql
   WHERE d.status = 'published'
     AND c.allowed_roles && ARRAY[:role]::text[]
   ORDER BY c.embedding <=> :query_embedding LIMIT 5
   ```

   Admins bypass the role filter. The answer, citations, and retrieval detail
   (`retrieved` vs `blocked`) are stored with the message.

## API overview

| Method & path | Purpose |
|---|---|
| `GET /api/health`, `GET /api/` | Health / service info |
| `POST /api/auth/change-password` | Change own password |
| `GET /api/auth/me` | Current user + profile |
| `POST /api/chat/conversations` | Create a conversation |
| `POST /api/chat/conversations/{id}/messages` | Ask a question in a conversation |
| `POST /api/chat/{id}/ask` | Ask (alias) |
| `GET /api/chat/conversations` · `GET /api/chat/conversations/{id}/messages` | History |
| `GET /api/admin/users` · `POST /api/admin/users/{id}/approve` · `POST /api/admin/users/{id}/role` | User admin |
| `GET /api/admin/documents` | Document list |
| `POST /api/admin/documents` | Upload (accepts txt/md/markdown/pdf/docx, max 20 MB) |
| `GET /api/admin/documents/{id}/chunks` | Chunk list (with `allowed_roles`) |
| `PATCH /api/admin/chunks/{id}` | Edit a chunk's `allowed_roles` |
| `POST /api/admin/documents/{id}/publish` | Publish a document |
| `POST /api/admin/documents/{id}/reset-chunk-roles` | Re-suggest roles for all chunks |
| `DELETE /api/admin/documents/{id}` | Delete a document |

## Getting started

Requirements: Python 3.11+, Node 20+, a Supabase project, and an NVIDIA NIM API key.

**Backend**

```bash
cd backend
python -m venv venv
# activate (Windows: .\venv\Scripts\Activate.ps1)
pip install -r requirements.txt
set .env / .env.example  # MANUAL, see "Environment"
uvicorn server:app --reload --port 8000
```

**Frontend**

```bash
cd frontend
npm install
npm start        # craco (CRA), http://localhost:3000
```

**Environment** (`backend/.env`, plus `frontend/.env` for `REACT_APP_*`):

| Variable | Extent | Notes |
|---|---|---|
| `DATABASE_URL` | backend | `postgresql+asyncpg://…` (Supabase) |
| `NIM_API_KEY` | backend | NVIDIA NIM key |
| `SUPABASE_URL` | backend | Used to fetch JWKS signing key |
| `CORS_ORIGINS` | backend | Default `https://rbac-rag-nine.vercel.app` |
| `NIM_BASE_URL` / `NIM_EMBED_MODEL` / `NIM_CHAT_MODEL` | backend | Optional overrides |
| `FRONTEND_BUILD_DIR` | backend | Path to the React build for SPA serving |
| `REACT_APP_SUPABASE_URL` / `REACT_APP_SUPABASE_ANON_KEY` | frontend | Build-time auth vars |
| `REACT_APP_BACKEND_URL` | frontend | API origin (empty = same origin) |

## Tests

Backend suite in `backend_test.py`. Run from `backend/`:

```bash
pytest
```

`pytest.ini` fixes xdist concurrency (`-n 2 --dist loadscope`); **do not** change `addopts`
or its plugins.

## Deployment

See **`DEPLOY_HF_SUPABASE.md`** for the full free-tier walkthrough:

1. Patient Supabase project + enable `vector` / `pgcrypto` extensions.
2. Push this repo and create a **Docker Space** (or Vercel).
3. Set the env secrets above (and `ADMIN_EMAIL` is not needed — the first admin is a manual SQL update).
4. The first admin is created via SQL (`update profiles set role='admin', status='approved' …`).

Tips: `DATABASE_SSL` is not read by the code; SSL is auto-enabled by `asyncpg`.
When deploying, prefer a **build step** that creates the React bundle before
the Docker Space starts (the repo's Dockerfile does this).

## Docs index

- [`PROJECT_STATUS.md`](PROJECT_STATUS.md) — what's built, what's not, and next steps.
- [`design_guidelines.md`](design_guidelines.md) — architecture/role decisions and conventions.
- [`DEPLOY_HF_SUPABASE.md`](DEPLOY_HF_SUPABASE.md) — free deployment on Hugging Face Spaces + Supabase.
- [`android_deep_links.md`](frontend/android_deep_links.md) — Android deep-link setup for the Capacitor app.
- [`archive/`](archive/) — superseded docs (implementation plan, hygiene audit).
