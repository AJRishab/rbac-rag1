# Sentry RAG — Project File Structure

Repository root: `C:\Users\AJRishab\Documents\rbac-rag`

> Generated/ignored directories omitted: `node_modules`, `.git`, `__pycache__`, `build`, `dist`, `.next`, `venv`. Secrets in `.env` files are not shown.

```
rbac-rag/                                   (repo root)
├── .cursor/settings.json
├── package-lock.json
└── RBAC-RAG/                               (the project)
    ├── .dockerignore
    ├── .gitignore
    ├── Dockerfile                          (HF Space: node build → python uvicorn :7860)
    ├── README.md
    ├── plan.md
    ├── design_guidelines.md
    ├── DEPLOY_HF_SUPABASE.md               (deploy guide — env vars, re-registration)
    ├── sentry-rag-chunk-level-tagging-addendum.md
    ├── requirements-space.txt
    │
    ├── backend/
    │   ├── .env                            (secrets — gitignored)
    │   ├── server.py                       (FastAPI app entry + SPA fallback)
    │   ├── database.py                     (engine, SCHEMA_SQL, init_db, migration apply)
    │   ├── auth.py                         (Supabase JWT verification)
    │   ├── deps.py                         (get_current_user / require_approved / require_admin)
    │   ├── schemas.py                      (Pydantic models)
    │   ├── ingest.py                       (parse/chunk docs)
    │   ├── nim_client.py                   (NVIDIA NIM embeddings/chat)
    │   ├── poc_rbac_rag.py                 (Phase-1 POC)
    │   ├── backend_test.py                 (black-box API test harness)
    │   ├── pytest.ini
    │   ├── requirements.txt
    │   ├── migrations/
    │   │   └── 001_supabase_auth.sql       (profiles, trigger, RLS, FK repoint)
    │   └── routers/
    │       ├── __init__.py
    │       ├── auth_router.py              (/auth/me, /change-password)
    │       ├── admin_router.py             (profiles, documents/chunks admin)
    │       └── chat_router.py              (RBAC RAG ask)
    │
    ├── frontend/
    │   ├── .env                            (REACT_APP_* — gitignored)
    │   ├── .gitignore
    │   ├── components.json
    │   ├── craco.config.js
    │   ├── jsconfig.json
    │   ├── tailwind.config.js
    │   ├── postcss.config.js
    │   ├── package.json
    │   ├── package-lock.json
    │   ├── README.md
    │   ├── public/
    │   │   └── index.html
    │   └── src/
    │       ├── index.js
    │       ├── App.js                      (routes incl. /verify-email, /auth/callback)
    │       ├── index.css
    │       ├── App.css
    │       ├── lib/
    │       │   ├── api.js                  (axios + Supabase session bearer)
    │       │   ├── supabaseClient.js
    │       │   └── utils.js
    │       ├── contexts/
    │       │   └── AuthContext.js          (signUp/signIn/signOut/session)
    │       ├── hooks/
    │       │   └── use-toast.js
    │       ├── constants/testIds/
    │       │   ├── index.js
    │       │   ├── sentry.js
    │       │   ├── auth.js
    │       │   └── home.js
    │       ├── pages/
    │       │   ├── Landing.js
    │       │   ├── Login.js
    │       │   ├── Register.js
    │       │   ├── VerifyEmail.js
    │       │   ├── AuthCallback.js         (email-verified → /login)
    │       │   ├── Pending.js              (awaiting approval + logout)
    │       │   ├── ChangePassword.js
    │       │   ├── Chat.js
    │       │   └── Admin.js
    │       ├── components/
    │       │   ├── ProtectedRoute.js
    │       │   ├── RoleBadge.js
    │       │   ├── MessageBubble.js
    │       │   ├── CitationChip.js
    │       │   ├── RetrievalDetailPanel.js
    │       │   ├── admin/
    │       │   │   ├── DocumentRow.js
    │       │   │   ├── UploadCard.js
    │       │   │   └── UserRows.js
    │       │   ├── chat/
    │       │   │   ├── ChatSidebar.js
    │       │   │   ├── EmptyState.js
    │       │   │   └── ThinkingBubble.js
    │       │   └── ui/                     (shadcn/ui primitives)
    │       │       ├── accordion.jsx alert.jsx alert-dialog.jsx aspect-ratio.jsx avatar.jsx
    │       │       ├── badge.jsx breadcrumb.jsx button.jsx calendar.jsx card.jsx
    │       │       ├── carousel.jsx checkbox.jsx collapsible.jsx command.jsx context-menu.jsx
    │       │       ├── dialog.jsx drawer.jsx dropdown-menu.jsx form.jsx hover-card.jsx
    │       │       ├── input.jsx input-otp.jsx label.jsx menubar.jsx navigation-menu.jsx
    │       │       ├── pagination.jsx popover.jsx progress.jsx radio-group.jsx resizable.jsx
    │       │       ├── scroll-area.jsx select.jsx separator.jsx sheet.jsx skeleton.jsx
    │       │       ├── slider.jsx sonner.jsx switch.jsx table.jsx tabs.jsx
    │       │       ├── textarea.jsx toast.jsx toaster.jsx toggle.jsx toggle-group.jsx
    │       │       └── tooltip.jsx
    │
    ├── scripts/
    │   └── bootstrap_postgres.sh           (PG15 + pgvector setup)
    │
    └── tests/
        └── __init__.py
```
