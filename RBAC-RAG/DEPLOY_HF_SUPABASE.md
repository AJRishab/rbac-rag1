# Deploy free: Hugging Face Spaces + Supabase

This repo is set up for a **Docker Space** that serves the React UI and the FastAPI
API on the same URL (port `7860`). Postgres + pgvector live on **Supabase**, and Auth
is **Supabase Auth** (JWT, verified in the backend via JWKS).

---

## Part A — Supabase (database)

### 1. Create a project
1. Go to [https://supabase.com](https://supabase.com) → sign in → **New project**
2. Pick a name, set a strong **Database password**, wait until the project is ready

### 2. Enable extensions
In the Supabase dashboard: **SQL Editor** → New query → run:

```sql
create extension if not exists vector;
create extension if not exists pgcrypto;
```

### 3. Get the connection string
1. **Project Settings** → **Database**
2. Under **Connection string**, choose **URI**
3. Prefer **Session mode** pooler (port 5432) or **Direct** connection if the pooler fails

Copy a URI like:

```text
postgresql://postgres.[PROJECT-REF]:[YOUR-PASSWORD]@aws-0-[REGION].pooler.supabase.com:5432/postgres
```

or:

```text
postgresql://postgres:[YOUR-PASSWORD]@db.[PROJECT-REF].supabase.co:5432/postgres
```

### 4. Convert for this app (asyncpg)
Change the scheme to `postgresql+asyncpg://`:

```text
postgresql+asyncpg://postgres.[PROJECT-REF]:[YOUR-PASSWORD]@aws-0-[REGION].pooler.supabase.com:5432/postgres
```

**Important**
- If the password has special characters (`@`, `#`, `%`, …), [URL-encode](https://www.urlencoder.org/) them.
- Keep this string private — you will paste it into Hugging Face **Secrets** only.

### 5. Tables are created automatically
On startup the backend creates `profiles`, `documents`, `chunks`, `conversations`,
`messages`, plus a `handle_new_user` trigger that inserts a `profiles` row when someone
signs up via Supabase Auth. The legacy `public.users` table is **no longer created**
(see Part B §5 if an old deployment left one behind).

---

## Part B — Hugging Face Space

### 1. Push this repo to Git
The Space SDK will pick up the existing `Dockerfile`.

### 2. Create the Space
- Go to [https://huggingface.co/new-space](https://huggingface.co/new-space)
- **SDK**: Docker
- Wait for the initial build to finish (it installs Python deps and builds the React SPA)

### 3. Set the Space secrets

Settings → **Variables and secrets**:

| Variable | Purpose | Notes |
|----------|---------|-------|
| `DATABASE_URL` | Postgres connection string (asyncpg) | Required. From Part A step 4 |
| `NIM_API_KEY` | NVIDIA NIM API key | Required |
| `SUPABASE_URL` | `https://<project-ref>.supabase.co` | Required — backend fetches the JWKS signing key from this |
| `REACT_APP_SUPABASE_URL` | Supabase URL (frontend build) | Required |
| `REACT_APP_SUPABASE_ANON_KEY` | Supabase anon key (frontend build) | Required |
| `CORS_ORIGINS` | Comma-separated origins allowed to call `/api` | Optional; defaults to `https://rbac-rag-nine.vercel.app` |
| `REACT_APP_BACKEND_URL` | Frontend API origin | Optional; empty = same-origin `/api` in the Space |

Optional overrides: `NIM_BASE_URL` (default `https://integrate.api.nvidia.com/v1`),
`NIM_EMBED_MODEL` (default `nvidia/nemotron-3-embed-1b`, 2048 dimensions), `NIM_CHAT_MODEL`,
`NIM_RERANK_MODEL` (set to an active NIM rerank model ID *for your key* — verify
with `curl -s https://integrate.api.nvidia.com/v1/models -H "Authorization: Bearer $NIM_API_KEY" | python3 -m json.tool | grep -i rerank`;
the default `nvidia/nv-rerankqa-mistral-4b-v3` is deprecated). At startup a
non-fatal reranker probe (disable via `RERANK_PROBE_ON_STARTUP=false`) logs a
loud error if the endpoint/model is misconfigured.

**SSL:** no `DATABASE_SSL` variable is read by the code; `asyncpg` enables TLS
automatically for `*.supabase.co` hostnames.

### 4. Create the first admin
Sign-up rows land in `profiles` via the trigger. Promote your account with a manual
SQL update (there is no auto-bootstrap admin):

```sql
update public.profiles
set role = 'admin', status = 'approved'
where email = 'you@example.com';
```

### 5. Legacy `users` table
If this Space was previously deployed against an old schema, drop the unused table once:

```sql
drop table if exists public.users;
```

### 6. Health check & smoke test

```bash
curl -s http://localhost:7860/api/health
curl -s http://localhost:7860/        # expects the React SPA (HTML)
```

**Serving note:** the backend serves the React build from `FRONTEND_BUILD_DIR`
(the Space Dockerfile sets it to `/app/frontend_build`). Static assets under
`public/` (like `.well-known/`) are **not** served by that static handler — put those
files on the platform that fronts the domain (e.g. Vercel) instead.

---

## Optional — deploying the frontend separately (Vercel)

You can run the SPA on Vercel and point `REACT_APP_BACKEND_URL` at the Space:

1. Vercel → **Add New…** → **Project** → import this repo.
2. Framework preset: **Create React App**; root directory `RBAC-RAG/frontend`.
3. Build command `npm run build`; output directory `build`.
4. Set Vercel env vars: `REACT_APP_BACKEND_URL` (the Space URL, e.g.
   `https://<space-name>.hf.space`), `REACT_APP_SUPABASE_URL`,
   `REACT_APP_SUPABASE_ANON_KEY`.
5. Allow that origin in the Space `CORS_ORIGINS`.
