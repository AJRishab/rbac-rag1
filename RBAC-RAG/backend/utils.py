"""Shared backend helpers (importable across routers, no app imports)."""


def fmt_vec(v: list[float]) -> str:
    """Format a float list as a pgvector text literal (see INSERT/CAST usage)."""
    return "[" + ",".join(f"{x:.7f}" for x in v) + "]"