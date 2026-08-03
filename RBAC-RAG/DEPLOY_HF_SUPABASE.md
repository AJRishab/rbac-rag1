# Deploy free: Hugging Face Spaces + Supabase

This repo is set up for a **Docker Space** that serves the React UI and FastAPI API on the same URL (port `7860`). Postgres + pgvector live on **Supabase**.

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

Click **Run**. You should see success.

### 3. Get the connection string
1. **Project Settings** → **Database**
2. Under **Connection string**, choose **URI**
3. Prefer **Session mode** pooler (port **5432**) or **Direct** connection if the pooler fails

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
- If the password has special characters (`@`, `#`, `%`, etc.), [URL-encode](https://www.urlencoder.org/) them
- Keep this string private — you will paste it into Hugging Face **Secrets** only

Tables (`users`, `documents`, `chunks`, …) are created automatically when the Space starts.

---

## Part B — Hugging Face Space

### 1. Push this repo to GitHub (or HF)
You need the project remote so the Space can build from it.

Example (from the `RBAC-RAG` folder):

```bash
git init
git add .
git commit -m "Prepare Hugging Face + Supabase deploy"
# create a GitHub repo, then:
git remote add origin https://github.com/YOUR_USER/YOUR_REPO.git
git branch -M main
git push -u origin main
```

Do **not** commit `.env` files (they contain secrets).

### 2. Create a Docker Space
1. Go to [https://huggingface.co/new-space](https://huggingface.co/new-space)
2. **Space name**: e.g. `sentry-rag`
3. **SDK**: **Docker**
4. **Hardware**: CPU basic (free)
5. Create the Space

### 3. Connect your code
**Option A — GitHub (easiest)**  
Space settings → **Repository** / sync from GitHub → select your repo (root must contain `Dockerfile`).

**Option B — HF git remote**

```bash
git remote add space https://huggingface.co/spaces/YOUR_HF_USER/sentry-rag
git push space main
```

(Use a [HF access token](https://huggingface.co/settings/tokens) with write access when prompted.)

### 4. Add Space secrets
In the Space: **Settings** → **Variables and secrets** → **New secret**

| Name | Value |
|------|--------|
| `DATABASE_URL` | Your `postgresql+asyncpg://...` string from Part A (use the service-role/owner connection — it bypasses RLS for the backend) |
| `NIM_API_KEY` | Your NVIDIA NIM key (`nvapi-...`) |
| `SUPABASE_JWT_SECRET` | Your Supabase project's JWT secret (Dashboard → Settings → API → JWT Secret). The backend uses this to verify Supabase-issued tokens. |
| `REACT_APP_SUPABASE_URL` | `https://<project-ref>.supabase.co` — needed at **frontend build** time to init `supabase-js` |
| `REACT_APP_SUPABASE_ANON_KEY` | Your project's public **anon** key (safe to expose client-side — RLS protects the data) |
| `CORS_ORIGINS` | `*` (same-origin UI is fine; `*` is simplest) |

Optional: `DATABASE_SSL=true` — auto-enabled when the URL contains `supabase.co`.

### 5. Wait for the build
Open the Space **Logs** / **Factory rebuild** if needed. First build installs Node + Python deps and can take **5–15 minutes**.

When ready, open:

```text
https://huggingface.co/spaces/YOUR_HF_USER/sentry-rag
```

or the direct app URL shown on the Space (often `*.hf.space`).

### 6. Accounts & first admin
Auth is now handled by **Supabase Auth** (client-side via `supabase-js`), not the
backend. New signups are `pending` with no role until an admin approves them.

- **New deploy:** open the app → **Create account** → sign up with an email +
  password. A `profiles` row is auto-created with `status = 'pending'` by the
  `handle_new_user` trigger.
- **Promote the first admin:** right after the first admin re-registers, run one
  SQL statement (Supabase SQL Editor) to approve them and assign the admin role,
  then they can approve everyone else through the admin console:
  ```sql
  update public.profiles set role = 'admin', status = 'approved'
  where email = 'your-admin-email@example.com';
  ```
- **Existing users (re-registration migration):** the old self-hosted `users`
  rows / bcrypt hashes can't be imported into Supabase Auth. Have each existing
  user sign up again with a new password; the admin matches them by email in
  `profiles` and re-approves / re-assigns their role.
- **Email confirmation:** keep **Confirm email** disabled (Authentication →
  Providers → Email) so login works immediately and the pending-approval flow
  is unchanged.
- **Legacy `users` table:** the backend now reads/writes `profiles` only. Once
  everyone has re-registered you can drop the old table (`drop table if exists
  public.users;`). `SCHEMA_SQL` recreates an empty `users` table on startup
  unless its block is later removed from `backend/database.py`.

Health check: `https://YOUR-SPACE-URL/api/health` → `{"status":"ok"}`

---

## How this deploy works

| Layer | Where |
|--------|--------|
| Auth / sessions | **Supabase Auth** (client-side `supabase-js`; backend verifies its JWT) |
| React UI | Built in Docker, served by FastAPI |
| FastAPI `/api/*` | Same Space container (port **7860**) |
| Postgres + pgvector | **Supabase** (RLS enabled, zero policies — backend uses the service-role connection) |
| Embeddings + chat | **NVIDIA NIM** (your API key) |

Same-origin means the browser calls `/api/...` on the Space URL — no separate frontend host.

---

## Local check before pushing (optional)

With Docker Desktop running:

```bash
cd RBAC-RAG
docker build -t sentry-rag .
docker run --rm -p 7860:7860 \
  -e DATABASE_URL="postgresql+asyncpg://..." \
  -e NIM_API_KEY="nvapi-..." \
  -e SUPABASE_JWT_SECRET="<supabase-jwt-secret>" \
  -e REACT_APP_SUPABASE_URL="https://<project-ref>.supabase.co" \
  -e REACT_APP_SUPABASE_ANON_KEY="<anon-key>" \
  sentry-rag
```

Open http://localhost:7860

---

## Free-tier gotchas

1. **Supabase** pauses after ~7 days of inactivity — open the project or hit the app to wake it
2. **HF Spaces** free CPU can sleep / be slow on cold start
3. **NIM** free tier rate-limits (~40 req/min) — large PDF uploads embed in batches and may need a pause/retry
4. Never put secrets in the README or commit `.env`

---

## Files added for this deploy

- `Dockerfile` — builds frontend + runs uvicorn on 7860  
- `requirements-space.txt` — slim Python deps for the Space  
- `.dockerignore` — keeps the image smaller  
- `README.md` — HF Space metadata (`sdk: docker`, `app_port: 7860`)
