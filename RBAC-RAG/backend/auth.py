"""Supabase Auth JWT verification.

The app no longer hashes passwords or issues tokens — Supabase Auth does.
We only verify the HS256-signed JWT that Supabase issues (signed with the
project's `SUPABASE_JWT_SECRET`) so the backend can trust the caller's
identity and read their `profiles` row.
"""
import os
import jwt

SUPABASE_JWT_SECRET = os.environ.get("SUPABASE_JWT_SECRET", "")


def verify_supabase_token(token: str) -> dict:
    """Verify a Supabase-issued JWT (HS256) and return its payload.

    Raises jwt.ExpiredSignatureError / jwt.InvalidTokenError on failure;
    callers map those to HTTP 401.
    """
    if not SUPABASE_JWT_SECRET:
        raise jwt.InvalidTokenError("SUPABASE_JWT_SECRET is not configured")
    return jwt.decode(token, SUPABASE_JWT_SECRET, algorithms=["HS256"])
