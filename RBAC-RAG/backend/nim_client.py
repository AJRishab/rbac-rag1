"""NVIDIA NIM API client with retry / 429 handling.

Core design:
- Lazy async client init guarded by asyncio.Lock so concurrent callers never race.
- Low-cyclomatic top-level entry (`_request_with_retry`) delegating to small helpers.
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

NIM_BASE_URL = os.environ.get("NIM_BASE_URL", "https://integrate.api.nvidia.com/v1")
# Nemotron-3 Embed returns 2048-dimensional vectors, matching the database
# schema and HNSW index. Keep this default aligned with `chunks.embedding`.
NIM_EMBED_MODEL = os.environ.get("NIM_EMBED_MODEL", "nvidia/nemotron-3-embed-1b")
# Llama 3.1 8B was retired by NVIDIA on 2026-08-26. Keep the fallback on
# the currently hosted successor; deployments can still override it via env.
NIM_CHAT_MODEL = os.environ.get("NIM_CHAT_MODEL", "meta/llama-3.3-70b-instruct")
# NIM reranker. Verified live against a real call:
#   POST https://ai.api.nvidia.com/v1/retrieval/nvidia/reranking  (HTTP 200)
#   model: nv-rerank-qa-mistral-4b:1  (short name + ":1" version suffix —
#          NOT the long-form "nvidia/rerank-qa-mistral-4b")
#   response: {"rankings":[{"index": N, "logit": <float>}, ...]} — the score
#   field is `logit` (a raw cross-entropy logit; monotonic with relevance),
#   which rerank() parses below.
NIM_RERANK_MODEL = os.environ.get("NIM_RERANK_MODEL", "nv-rerank-qa-mistral-4b:1")

# Base HOST of the reranker endpoint. The reranker is served from a DIFFERENT
# host (ai.api.nvidia.com) than the chat/embed NIM_BASE_URL
# (integrate.api.nvidia.com), so this must NOT derive from or fall back to it.
# The canonical rerank path is appended in `_rerank_endpoint()` below and is
# de-duplicated, so you may set either a bare host
# (https://ai.api.nvidia.com) or a full endpoint URL.
NIM_RERANK_BASE_URL = (
    os.environ.get("NIM_RERANK_BASE_URL")
    or "https://ai.api.nvidia.com"
).rstrip("/")
# Canonical rerank route appended to NIM_RERANK_BASE_URL.
NIM_RERANK_PATH = (
    f"/v1/retrieval/nvidia/"
    f"{NIM_RERANK_MODEL.removeprefix('nvidia/')}/reranking"
)


def _rerank_endpoint() -> str:
    base = NIM_RERANK_BASE_URL.rstrip("/")
    if base.endswith(NIM_RERANK_PATH):
        return base
    return base + NIM_RERANK_PATH


# Full URL the client POSTs to (computed once so logs show the real target).
NIM_RERANK_ENDPOINT: str = _rerank_endpoint()


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


async def rerank(query: str, documents: list[str], top_n: int = 50) -> list[dict]:
    """Rerank documents against a query via the NIM reranking endpoint.

    POSTs to ``NIM_RERANK_ENDPOINT`` (``NIM_RERANK_BASE_URL`` + the canonical
    rerank route ``/v1/retrieval/nvidia/reranking``, de-duplicated). The
    reranker host differs from ``NIM_BASE_URL`` and is NOT derived from it.
    The model is the short name + version, e.g. ``nv-rerank-qa-mistral-4b:1``.

    The live response is ``{"rankings":[{"index": N, "logit": <float>}, ...]}``:
    the score field is ``logit`` (a raw cross-entropy logit, monotonic with
    relevance). ``relevance_score``/``score``/``logprob`` are also accepted so
    the parser works across deployments; any unrecognized shape raises loudly
    so a misconfigured key/model degrades instead of silently returning RRF order.

    .. code-block:: json

        {
          "model": "nv-rerank-qa-mistral-4b:1",
          "query": {"text": "<question>"},
          "passages": [{"text": "<chunk 1>"}, {"text": "<chunk 2>"}],
          "truncate": "END"
        }

    Returns ``[{"index": int, "relevance_score": float}]`` sorted by score
    descending, truncated to ``top_n``. ``index`` is the position in
    ``documents`` so the caller can map scores back onto chunks.
    """
    if not documents:
        return []
    data = await _request_with_retry(
        "POST",
        NIM_RERANK_ENDPOINT,
        json_body={
            "model": NIM_RERANK_MODEL,
            "query": {"text": query},
            "passages": [{"text": doc} for doc in documents],
            "truncate": "END",
        },
    )

    # Expected (live, verified): {"rankings": [{"index": N, "logit": <float>}, ...]}.
    # The score key varies by deployment; accept in priority order
    # relevance_score -> score -> logprob -> logit. Fail LOUDLY on any
    # unexpected shape instead of silently returning nothing and degrading.
    rankings = data.get("rankings")
    if not isinstance(rankings, list):
        raise RuntimeError(
            f"NIM ranking response has no 'rankings' list (model={NIM_RERANK_MODEL}): "
            f"{str(data)[:400]}"
        )
    scored: list[dict] = []
    for item in rankings:
        if not isinstance(item, dict) or "index" not in item:
            raise RuntimeError(
                f"NIM ranking item missing 'index' key (model={NIM_RERANK_MODEL}): {item!r}"
            )
        score_value = item.get(
            "relevance_score",
            item.get("score", item.get("logprob", item.get("logit"))),
        )
        if score_value is None:
            raise RuntimeError(
                f"NIM ranking item has no score/logprob/logit/relevance_score key "
                f"(model={NIM_RERANK_MODEL}): {item!r}"
            )
        try:
            scored.append({"index": int(item["index"]), "relevance_score": float(score_value)})
        except (TypeError, ValueError):
            raise RuntimeError(
                f"NIM ranking item index/score not numeric (model={NIM_RERANK_MODEL}): {item!r}"
            )
    scored.sort(key=lambda x: x["relevance_score"], reverse=True)
    return scored[:top_n]


async def probe_reranker() -> tuple[bool, str]:
    """Validate the NIM reranker endpoint + NIM_RERANK_MODEL with a minimal call
    (live target: ai.api.nvidia.com/v1/retrieval/nvidia/reranking).

    Returns ``(ok, detail)`` and never raises, so callers (e.g. the startup
    health check) can log the outcome loudly without crashing the app.
    """
    try:
        out = await rerank("probe", ["probe"], top_n=1)
        if not out:
            return False, "ranking call returned no results"
        return True, "ok"
    except Exception as exc:  # noqa: BLE001 - probe reports, never raises
        return False, getattr(exc, "detail", None) or str(exc)


def _parse_role_suggestions(response: str, expected_count: int, candidate_roles: list[str]) -> list[list[str] | None]:
    """Parse a model response without allowing it to expand the role ceiling.

    ``None`` means that chunk must use the caller's fail-safe default.
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
        logger.warning("NIM returned malformed chunk-role suggestions; using document defaults")
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

    # Around 500 tokens per chunk are produced by ingestion. Keep prompts well
    # below common instruction-model context limits while retaining batch calls.
    max_chars = int(os.environ.get("NIM_CHUNK_ROLE_BATCH_CHARS", "24000"))
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
            "Return exactly {\"chunk_roles\":[{\"index\":0,\"roles\":[\"role\"]}]} for every index."
        )
        try:
            response = await chat(system, prompt, max_tokens=max(300, len(batch) * 40), temperature=0)
            parsed = _parse_role_suggestions(response, len(batch), defaults)
        except Exception as exc:  # Upload must not be blocked by advisory tagging.
            logger.warning("Chunk role suggestion failed; using document defaults: %s", type(exc).__name__)
            parsed = [None] * len(batch)
        all_roles.extend(item if item is not None else defaults.copy() for item in parsed)
    return all_roles
