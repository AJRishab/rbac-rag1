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
| `DATABASE_URL` | Your `postgresql+asyncpg://...` string from Part A |
| `NIM_API_KEY` | Your NVIDIA NIM key (`nvapi-...`) |
| `JWT_SECRET` | Long random string (e.g. 32+ chars) |
| `ADMIN_EMAIL` | `admin@sentry.local` (or your email) |
| `ADMIN_PASSWORD` | Strong password for first admin login |
| `CORS_ORIGINS` | `*` (same-origin UI is fine; `*` is simplest) |

Optional: `DATABASE_SSL=true` — auto-enabled when the URL contains `supabase.co`.

### 5. Wait for the build
Open the Space **Logs** / **Factory rebuild** if needed. First build installs Node + Python deps and can take **5–15 minutes**.

When ready, open:

```text
https://huggingface.co/spaces/YOUR_HF_USER/sentry-rag
```

or the direct app URL shown on the Space (often `*.hf.space`).

### 6. Log in
Use `ADMIN_EMAIL` / `ADMIN_PASSWORD` from secrets.  
Then upload documents and chat as usual.

Health check: `https://YOUR-SPACE-URL/api/health` → `{"status":"ok"}`

---

## How this deploy works

| Layer | Where |
|--------|--------|
| React UI | Built in Docker, served by FastAPI |
| FastAPI `/api/*` | Same Space container (port **7860**) |
| Postgres + pgvector | **Supabase** |
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
  -e JWT_SECRET="dev-secret" \
  -e ADMIN_EMAIL="admin@sentry.local" \
  -e ADMIN_PASSWORD="admin123" \
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
