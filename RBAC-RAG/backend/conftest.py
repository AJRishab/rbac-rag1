"""Hermetic test environment: set required env vars before any app module import.

The app modules (database.py reads DATABASE_URL at import; auth.py reads
SUPABASE_URL) require these to be present. Tests never connect to a real
database or NIM endpoint - they use fakes, so the values are placeholders.
"""
import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test")
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("OPENROUTER_API_KEY", "test-nim-key")
