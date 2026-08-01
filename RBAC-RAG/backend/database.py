"""Database engine, session, schema init, seed default admin."""
import os
import secrets
import string
import logging
from pathlib import Path
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env", override=True)

DATABASE_URL = os.environ["DATABASE_URL"]

# Supabase (and most hosted Postgres) requires SSL.
_connect_args = {}

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    pass


logger = logging.getLogger(__name__)

# Schema init statements (idempotent)
SCHEMA_SQL = [
    "CREATE EXTENSION IF NOT EXISTS vector",
    "CREATE EXTENSION IF NOT EXISTS pgcrypto",

    """CREATE TABLE IF NOT EXISTS users (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        email text UNIQUE NOT NULL,
        password_hash text NOT NULL,
        role text,
        status text NOT NULL DEFAULT 'pending',
        must_change_password boolean NOT NULL DEFAULT false,
        created_at timestamptz NOT NULL DEFAULT now()
    )""",

    """CREATE TABLE IF NOT EXISTS documents (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        title text NOT NULL,
        filename text NOT NULL,
        uploaded_by uuid REFERENCES users(id) ON DELETE SET NULL,
        allowed_roles text[] NOT NULL DEFAULT ARRAY[]::text[],
        status text NOT NULL DEFAULT 'pending_review' CHECK (status IN ('pending_review', 'published')),
        chunk_count int NOT NULL DEFAULT 0,
        uploaded_at timestamptz NOT NULL DEFAULT now()
    )""",

    """CREATE TABLE IF NOT EXISTS chunks (
        id bigserial PRIMARY KEY,
        document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
        chunk_index int NOT NULL,
        content text NOT NULL,
        embedding vector(1024) NOT NULL,
        allowed_roles text[] NOT NULL DEFAULT ARRAY[]::text[],
        roles_ai_suggested boolean NOT NULL DEFAULT true,
        source_page int
    )""",

    # Idempotent upgrades for databases created before chunk-level review.
    "ALTER TABLE documents ADD COLUMN IF NOT EXISTS status text NOT NULL DEFAULT 'pending_review'",
    "ALTER TABLE chunks ADD COLUMN IF NOT EXISTS roles_ai_suggested boolean NOT NULL DEFAULT true",
    "ALTER TABLE chunks ADD COLUMN IF NOT EXISTS source_page int",

    "CREATE INDEX IF NOT EXISTS chunks_roles_gin ON chunks USING GIN (allowed_roles)",
    "CREATE INDEX IF NOT EXISTS chunks_document_id_idx ON chunks (document_id)",

    """CREATE TABLE IF NOT EXISTS conversations (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        title text NOT NULL DEFAULT 'New conversation',
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now()
    )""",

    "CREATE INDEX IF NOT EXISTS conversations_user_updated_idx ON conversations (user_id, updated_at DESC)",

    """CREATE TABLE IF NOT EXISTS messages (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        conversation_id uuid NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
        role text NOT NULL,
        content text NOT NULL,
        citations jsonb,
        retrieved_count int,
        blocked_count int,
        retrieval_detail jsonb,
        created_at timestamptz NOT NULL DEFAULT now()
    )""",

    "CREATE INDEX IF NOT EXISTS messages_conv_created_idx ON messages (conversation_id, created_at)",
]


def _generate_password(length: int = 16) -> str:
    alphabet = string.ascii_letters + string.digits + "@#!$%^&*"
    return "".join(secrets.choice(alphabet) for _ in range(length))


async def init_db():
    """Create schema (idempotent) + seed default admin."""
    async with engine.begin() as conn:
        for stmt in SCHEMA_SQL:
            await conn.execute(text(stmt))

    # Seed default admin
    from auth import hash_password
    async with SessionLocal() as session:
        result = await session.execute(text("SELECT COUNT(*) FROM users WHERE role = 'admin'"))
        admin_count = result.scalar()

        if admin_count == 0:
            admin_email = os.environ.get("ADMIN_EMAIL", "admin@sentry.local").strip() or "admin@sentry.local"
            admin_password_env = os.environ.get("ADMIN_PASSWORD", "").strip()
            if admin_password_env:
                admin_password = admin_password_env
                must_change = False
            else:
                admin_password = _generate_password()
                must_change = True

            pwd_hash = hash_password(admin_password)
            await session.execute(
                text(
                    "INSERT INTO users (email, password_hash, role, status, must_change_password) "
                    "VALUES (:e, :p, 'admin', 'approved', :m) "
                    "ON CONFLICT (email) DO NOTHING"
                ),
                {"e": admin_email, "p": pwd_hash, "m": must_change},
            )
            await session.commit()

            banner = "=" * 70
            logger.warning("\n%s\nSENTRY RAG - DEFAULT ADMIN SEEDED\n%s\nEmail:    %s\nPassword: %s\nMust change on first login: %s\n%s\n", banner, banner, admin_email, admin_password, must_change, banner)
