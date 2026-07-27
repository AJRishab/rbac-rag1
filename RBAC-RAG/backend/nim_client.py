"""NVIDIA NIM API client with retry / 429 handling.

Core design:
- Lazy async client init guarded by asyncio.Lock so concurrent callers never race.
- Low-cyclomatic top-level entry (`_request_with_retry`) delegating to small helpers.
"""
import os
import asyncio
import logging
from pathlib import Path
import httpx
from dotenv import load_dotenv
from fastapi import HTTPException

load_dotenv(Path(__file__).parent / ".env", override=True)

logger = logging.getLogger(__name__)

NIM_BASE_URL = os.environ.get("NIM_BASE_URL", "https://integrate.api.nvidia.com/v1")
NIM_EMBED_MODEL = os.environ.get("NIM_EMBED_MODEL", "nvidia/nv-embedqa-e5-v5")
NIM_CHAT_MODEL = os.environ.get("NIM_CHAT_MODEL", "meta/llama-3.1-8b-instruct")

# Explicitly initialized on all code paths.
_client: httpx.AsyncClient | None = None
_client_lock: asyncio.Lock | None = None


def _lock() -> asyncio.Lock:
    """Return the singleton lock; lazily created on first use."""
    global _client_lock
    if _client_lock is None:
        _client_lock = asyncio.Lock()
    return _client_lock


async def _get_client() -> httpx.AsyncClient:
    """Return a live shared AsyncClient. Safe under concurrent callers."""
    global _client
    if _client is not None:
        return _client
    async with _lock():
        if _client is None:
            _client = httpx.AsyncClient(timeout=httpx.Timeout(90.0, connect=15.0))
    return _client


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


# ---------------- Helpers for _request_with_retry ----------------


def _headers() -> dict:
    api_key = os.environ.get("NIM_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(status_code=500, detail="NIM_API_KEY is not configured")
    return {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def _handle_status(r: httpx.Response) -> tuple[bool, HTTPException | None]:
    """Classify a NIM response.

    Returns (should_retry, terminal_error).
    - (False, None): success — caller should return r.json().
    - (True, None):  transient (429 / 5xx) — caller should retry.
    - (False, exc):  terminal client error — caller should raise `exc`.
    """
    if r.status_code == 200:
        return False, None
    if r.status_code == 429:
        return True, None
    if r.status_code >= 500:
        return True, None
    return False, HTTPException(
        status_code=502,
        detail=f"NIM API error {r.status_code}: {r.text[:300]}",
    )


def _terminal_error_for_exception(exc: Exception, attempt: int) -> HTTPException | None:
    """Map a transport-level exception to a terminal HTTPException when we've
    exhausted retries. Returns None to signal 'retry again'.
    """
    if isinstance(exc, httpx.TimeoutException):
        return HTTPException(status_code=504, detail="LLM request timed out. Please try again.")
    return HTTPException(status_code=502, detail=f"LLM request failed: {type(exc).__name__}")


async def _request_with_retry(
    method: str,
    url: str,
    *,
    json_body: dict,
    max_retries: int = 2,
    retry_backoff: float = 2.0,
) -> dict:
    client = await _get_client()
    last_exc: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            r = await client.request(method, url, headers=_headers(), json=json_body)
        except (httpx.TimeoutException, httpx.HTTPError) as e:
            last_exc = e
            logger.warning("NIM transport error (attempt %d): %s", attempt + 1, e)
            if attempt == max_retries:
                raise _terminal_error_for_exception(e, attempt)
            await asyncio.sleep(retry_backoff * (attempt + 1))
            continue

        should_retry, terminal = _handle_status(r)
        if terminal is not None:
            raise terminal
        if not should_retry:
            return r.json()

        # 429 / 5xx — log and (maybe) retry
        logger.warning("NIM transient status %s (attempt %d)", r.status_code, attempt + 1)
        if attempt == max_retries:
            if r.status_code == 429:
                raise HTTPException(
                    status_code=429,
                    detail="LLM rate limit reached (NIM free tier ~40 req/min). Please wait a few seconds and try again.",
                )
            raise HTTPException(
                status_code=502,
                detail=f"NIM upstream error {r.status_code}: {r.text[:200]}",
            )
        await asyncio.sleep(retry_backoff * (attempt + 1))

    # Defensive fallthrough (loop always returns or raises)
    raise HTTPException(status_code=502, detail=f"NIM request failed after retries: {last_exc}")


# ---------------- Public API ----------------


async def embed(texts: list[str], input_type: str = "passage") -> list[list[float]]:
    """Batch-embed a list of texts. NIM E5 requires input_type=passage|query."""
    if not texts:
        return []
    batch_size = 32
    all_embeddings: list[list[float]] = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        data = await _request_with_retry(
            "POST",
            f"{NIM_BASE_URL}/embeddings",
            json_body={
                "input": batch,
                "model": NIM_EMBED_MODEL,
                "input_type": input_type,
                "encoding_format": "float",
                "truncate": "END",
            },
        )
        all_embeddings.extend(d["embedding"] for d in data["data"])
    return all_embeddings


async def chat(system: str, user: str, max_tokens: int = 700, temperature: float = 0.2) -> str:
    data = await _request_with_retry(
        "POST",
        f"{NIM_BASE_URL}/chat/completions",
        json_body={
            "model": NIM_CHAT_MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "top_p": 0.9,
            "max_tokens": max_tokens,
        },
    )
    return data["choices"][0]["message"]["content"]
