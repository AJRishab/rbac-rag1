"""Database engine, session, schema init, Supabase Auth migration."""
import os
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

    """CREATE TABLE IF NOT EXISTS documents (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        title text NOT NULL,
        filename text NOT NULL,
        uploaded_by uuid,
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
        user_id uuid NOT NULL,
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


def _split_sql(sql: str) -> list[str]:
    """Split a SQL script into statements, respecting `$$...$$` and '...' blocks."""
    statements: list[str] = []
    current: list[str] = []
    in_dollar = False
    in_squote = False
    i = 0
    n = len(sql)
    while i < n:
        # SQL `--` line comment (outside strings / dollar quotes): skip to EOL so
        # apostrophes inside comments can't corrupt single-quote state.
        if not in_squote and not in_dollar and sql[i:i + 2] == "--":
            while i < n and sql[i] != "\n":
                i += 1
            continue
        if not in_squote and sql[i:i + 2] == "$$":
            in_dollar = not in_dollar
            current.append("$$")
            i += 2
            continue
        ch = sql[i]
        if ch == "'" and not in_dollar:
            in_squote = not in_squote
            current.append(ch)
            i += 1
            continue
        if ch == ";" and not in_dollar and not in_squote:
            stmt = "".join(current).strip()
            if stmt:
                statements.append(stmt)
            current = []
            i += 1
            continue
        current.append(ch)
        i += 1
    last = "".join(current).strip()
    if last:
        statements.append(last)
    return statements


async def init_db():
    """Create the schema (idempotent) and apply the Supabase Auth migration.

    Identity now lives in public.profiles (mirroring Supabase's auth.users);
    the legacy users table is deprecated and no longer read or written by the
    app. Admin / user accounts are created through Supabase Auth (client-side
    signup) — there is no backend password seed anymore.
    """
    async with engine.begin() as conn:
        for stmt in SCHEMA_SQL:
            await conn.execute(text(stmt))

        # Supabase Auth migration: profiles, new-user trigger, FK repoint, RLS.
        # Idempotent. Statements run individually so a plain Postgres dev DB
        # (no Supabase auth schema) skips only the auth-dependent ones.
        migration_path = Path(__file__).parent / "migrations" / "001_supabase_auth.sql"
        if migration_path.is_file():
            migration_sql = migration_path.read_text(encoding="utf-8")
            for stmt in _split_sql(migration_sql):
                try:
                    await conn.execute(text(stmt))
                except Exception as exc:  # e.g. no auth.users on plain Postgres
                    logger.warning(
                        "Supabase auth migration statement skipped (%s): %s",
                        type(exc).__name__, exc,
                    )
