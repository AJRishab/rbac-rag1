"""OpenRouter API client with retry / rate-limit handling.

Replaces the former NVIDIA NIM client. The public function names
(``embed``/``chat``/``rerank``/``suggest_chunk_roles``/``probe_reranker``/
``close_client``) are kept identical so the routers and summarizer need no
changes beyond the import/constant renames.

OpenRouter is OpenAI-compatible for chat + embeddings, plus a dedicated
Cohere-style rerank endpoint on the same base URL.

Design (carried over from the NIM client):
- Lazy async client init guarded by asyncio.Lock so concurrent callers never race.
- Low-cyclomatic top-level entry (:func:`_request_with_retry`) delegating to helpers.
- Transient 429/5xx and provider-overload (529) are retried with backoff.
"""
import os
import asyncio
import json
import logging
from pathlib import Path
import httpx
from dotenv import load_dotenv
from fastapi import HTTPException

load_dotenv(Path(__file__).parent / ".env", override=True)

logger = logging.getLogger(__name__)

# OpenAI-compatible base URL for chat + embeddings.
OPENROUTER_BASE_URL = os.environ.get(
    "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
).rstrip("/")

# Embeddings — lfm-2.5-embedding-350m outputs 1024-dim vectors. This MUST match the
# `chunks.embedding vector(1024)` column (see migrations/005_*).
OPENROUTER_EMBED_MODEL = os.environ.get(
    "OPENROUTER_EMBED_MODEL", "liquid/lfm-2.5-embedding-350m:free"
)
# Chat model (OpenAI-compatible).
OPENROUTER_CHAT_MODEL = os.environ.get("OPENROUTER_CHAT_MODEL", "google/gemma-4-31b-it:free")

# Rerank model + endpoint. OpenRouter rerank is Cohere-style:
#   POST {OPENROUTER_BASE_URL}/rerank
#   body: {"model","query","documents","top_n"}
#   response: {"results":[{"index":N,"relevance_score":<float>}, ...]}
OPENROUTER_RERANK_MODEL = os.environ.get("OPENROUTER_RERANK_MODEL", "nvidia/llama-nemotron-rerank-vl-1b-v2:free")
OPENROUTER_RERANK_ENDPOINT = f"{OPENROUTER_BASE_URL}/rerank"

# Optional OpenRouter attribution headers (shown in their dashboard).
OPENROUTER_REFERER = os.environ.get("OPENROUTER_REFERER", "")
OPENROUTER_TITLE = os.environ.get("OPENROUTER_TITLE", "Sentry RAG")


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


# ---------------- Retry / error helpers ----------------


def _headers() -> dict:
    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(status_code=500, detail="OPENROUTER_API_KEY is not configured")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-Title": OPENROUTER_TITLE,
    }
    if OPENROUTER_REFERER:
        headers["HTTP-Referer"] = OPENROUTER_REFERER
    return headers


def _handle_status(r: httpx.Response) -> tuple[bool, str]:
    """Classify a response. Returns (should_retry, error_detail).

    - (False, ""):  success.
    - (True,  ""):  transient (429/5xx/529) — caller should retry.
    - (False, msg): terminal client error — caller should raise.
    """
    if r.status_code == 200:
        return False, ""
    if r.status_code == 429 or r.status_code >= 500:
        return True, ""
    return False, f"OpenRouter API error {r.status_code}: {r.text[:300]}"


def _raise_transport_error(exc: Exception) -> HTTPException:
    if isinstance(exc, httpx.TimeoutException):
        return HTTPException(status_code=504, detail="LLM request timed out. Please try again.")
    return HTTPException(status_code=502, detail=f"LLM request failed: {type(exc).__name__}")


async def _request_with_retry(
    url: str,
    json_body: dict,
    *,
    max_retries: int = 2,
    retry_backoff: float = 2.0,
) -> dict:
    client = await _get_client()
    last_exc: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            r = await client.post(url, headers=_headers(), json=json_body)
        except (httpx.TimeoutException, httpx.HTTPError) as e:
            last_exc = e
            logger.warning("OpenRouter transport error (attempt %d): %s", attempt + 1, e)
            if attempt == max_retries:
                raise _raise_transport_error(e)
            await asyncio.sleep(retry_backoff * (attempt + 1))
            continue

        should_retry, err = _handle_status(r)
        if err:
            raise HTTPException(status_code=502, detail=err)
        if not should_retry:
            return r.json()

        # transient 429 / 5xx / 529
        logger.warning("OpenRouter transient status %s (attempt %d)", r.status_code, attempt + 1)
        if attempt == max_retries:
            if r.status_code == 429:
                raise HTTPException(
                    status_code=429,
                    detail="LLM rate limit reached. Please wait a few seconds and try again.",
                )
            raise HTTPException(
                status_code=502,
                detail=f"OpenRouter upstream error {r.status_code}: {r.text[:200]}",
            )
        await asyncio.sleep(retry_backoff * (attempt + 1))

    # Defensive fallthrough (loop always returns or raises).
    raise HTTPException(status_code=502, detail=f"OpenRouter request failed after retries: {last_exc}")


# ---------------- Public API ----------------


async def embed(texts: list[str], input_type: str = "passage") -> list[list[float]]:
    """Batch-embed a list of texts via OpenRouter (OpenAI-compatible).

    ``input_type`` is accepted for backwards compatibility with the NIM-era
    signature but is ignored — OpenRouter embed models (e.g. lfm-2.5-embedding-350m)
    do not require a passage/query flag.
    """
    if not texts:
        return []
    batch_size = 32
    all_vecs: list[list[float]] = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        data = await _request_with_retry(
            f"{OPENROUTER_BASE_URL}/embeddings",
            {"input": batch, "model": OPENROUTER_EMBED_MODEL},
        )
        items = data.get("data") or []
        items.sort(key=lambda d: d.get("index", 0))
        all_vecs.extend(d["embedding"] for d in items if "embedding" in d)
    return all_vecs


async def chat(system: str, user: str, max_tokens: int = 700, temperature: float = 0.2) -> str:
    data = await _request_with_retry(
        f"{OPENROUTER_BASE_URL}/chat/completions",
        json_body={
            "model": OPENROUTER_CHAT_MODEL,
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


async def rerank(query: str, documents: list[str], top_n: int = 50) -> list[dict]:
    """Rerank documents against a query via the OpenRouter Cohere-style endpoint.

    Returns ``[{"index": int, "relevance_score": float}]`` sorted by score
    descending, truncated to ``top_n``. ``index`` is the position in
    ``documents`` so the caller can map scores back onto chunks.

    Expected response: ``{"results":[{"index":N,"relevance_score":<f>}, ...]}``
    (a ``data`` key is also tolerated). Parse failures raise loudly rather than
    silently degrading to RRF order.
    """
    if not documents:
        return []
    data = await _request_with_retry(
        OPENROUTER_RERANK_ENDPOINT,
        json_body={
            "model": OPENROUTER_RERANK_MODEL,
            "query": query,
            "documents": documents,
            "top_n": top_n,
        },
    )
    results = data.get("results", data.get("data"))
    if not isinstance(results, list):
        raise RuntimeError(
            f"OpenRouter rerank response has no 'results'/'data' list "
            f"(model={OPENROUTER_RERANK_MODEL}): {str(data)[:400]}"
        )
    scored: list[dict] = []
    for item in results:
        if not isinstance(item, dict) or "index" not in item:
            raise RuntimeError(
                f"OpenRouter rerank item missing 'index' key "
                f"(model={OPENROUTER_RERANK_MODEL}): {item!r}"
            )
        score = item.get("relevance_score", item.get("score"))
        if score is None:
            raise RuntimeError(
                f"OpenRouter rerank item has no relevance_score/score key "
                f"(model={OPENROUTER_RERANK_MODEL}): {item!r}"
            )
        try:
            scored.append({"index": int(item["index"]), "relevance_score": float(score)})
        except (TypeError, ValueError):
            raise RuntimeError(
                f"OpenRouter rerank item index/score not numeric "
                f"(model={OPENROUTER_RERANK_MODEL}): {item!r}"
            )
    scored.sort(key=lambda x: x["relevance_score"], reverse=True)
    return scored[:top_n]


async def probe_reranker() -> tuple[bool, str]:
    """Validate the OpenRouter rerank endpoint + model with a minimal call.

    Returns ``(ok, detail)`` and never raises, so callers (e.g. the startup
    health check) can log the outcome loudly without crashing the app.
    """
    try:
        out = await rerank("probe", ["probe"], top_n=1)
        if not out:
            return False, "rerank call returned no results"
        return True, "ok"
    except Exception as exc:  # noqa: BLE001 - probe reports, never raises
        return False, getattr(exc, "detail", None) or str(exc)


def _parse_role_suggestions(
    response: str, expected_count: int, candidate_roles: list[str]
) -> list[list[str] | None]:
    """Parse a model response without allowing it to expand the role ceiling.

    Falls back to ``None`` (caller substitutes the document default) on any
    malformed or out-of-bounds item. Never trusts model-provided roles.
    """
    suggestions: list[list[str] | None] = [None] * expected_count
    try:
        payload = json.loads(response)
        items = payload["chunk_roles"]
        if not isinstance(items, list):
            return suggestions
        seen: set[int] = set()
        allowed = set(candidate_roles)
        for item in items:
            if not isinstance(item, dict):
                continue
            index, roles = item.get("index"), item.get("roles")
            if not isinstance(index, int) or index < 0 or index >= expected_count or index in seen:
                continue
            seen.add(index)
            if not isinstance(roles, list) or not roles or any(not isinstance(role, str) for role in roles):
                continue
            normalized = sorted(set(roles))
            if any(role not in allowed for role in normalized):
                continue
            suggestions[index] = normalized
    except (json.JSONDecodeError, KeyError, TypeError):
        logger.warning("OpenRouter returned malformed chunk-role suggestions; using document defaults")
    return suggestions


async def suggest_chunk_roles(chunks: list[str], candidate_roles: list[str]) -> list[list[str]]:
    """Suggest a permitted role subset per chunk, with a safe per-chunk fallback.

    The model is deliberately called in bounded batches, never once per chunk. A
    failure or invalid item falls back to the document's candidate roles so upload
    remains available and no model output can grant additional access.
    """
    defaults = sorted(set(candidate_roles))
    if not chunks or not defaults:
        return [defaults.copy() for _ in chunks]

    # ~500 tokens per chunk from ingestion. Keep prompts well below common
    # instruction-model context limits while retaining batch calls.
    max_chars = int(os.environ.get("OPENROUTER_CHUNK_ROLE_BATCH_CHARS", "24000"))
    batches: list[list[str]] = []
    batch: list[str] = []
    size = 0
    for chunk in chunks:
        chunk_size = len(chunk) + 32
        if batch and size + chunk_size > max_chars:
            batches.append(batch)
            batch, size = [], 0
        batch.append(chunk)
        size += chunk_size
    if batch:
        batches.append(batch)

    all_roles: list[list[str]] = []
    system = (
        "You assign document-access roles for RAG chunks. Return JSON only, with no markdown. "
        "Choose a non-empty subset of the candidate roles for every chunk. Use all candidate roles "
        "unless a chunk is clearly more sensitive (for example named pay, health, discipline, or legal details). "
        "Never invent roles or omit an index."
    )
    for batch in batches:
        numbered = "\n\n".join(f"[{index}] {chunk}" for index, chunk in enumerate(batch))
        prompt = (
            f"Candidate roles: {json.dumps(defaults)}\n\nChunks:\n{numbered}\n\n"
            'Return exactly {"chunk_roles":[{"index":0,"roles":["role"]}]} for every index.'
        )
        try:
            response = await chat(system, prompt, max_tokens=max(300, len(batch) * 40), temperature=0)
            parsed = _parse_role_suggestions(response, len(batch), defaults)
        except Exception as exc:  # Upload must not be blocked by advisory tagging.
            logger.warning("Chunk role suggestion failed; using document defaults: %s", type(exc).__name__)
            parsed = [None] * len(batch)
        all_roles.extend(item if item is not None else defaults.copy() for item in parsed)
    return all_roles
