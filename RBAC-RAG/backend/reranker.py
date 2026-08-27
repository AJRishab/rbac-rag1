"""Reranking stage: NIM cross-encoder over the fused, RBAC-checked candidates.

Takes the fused candidate list from :mod:`retrieval` and the original query,
calls the NIM reranker, and returns the same chunks reordered by relevance
score with ``rerank_score`` / ``rerank_rank`` populated.

On reranker failure the pipeline degrades to the input (RRF) order so chat
stays available — but the FIRST failure logs a loud, complete diagnostic
(including HTTP status/body when available, plus the configured model and
endpoint) so a misconfigured ``OPENROUTER_RERANK_MODEL`` or wrong endpoint is obvious
in the logs instead of silently degrading every request forever. A startup
probe in ``server.py`` surfaces the same problem at boot.
"""
import logging

import openrouter
from retrieval import RetrievedChunk

logger = logging.getLogger(__name__)

RERANK_TOP_N = 20  # candidate pool fed to the reranker

# Flip once so the FULL diagnostic is written exactly once, then demoted to a
# single-line warning on subsequent failures.
_RERANK_FAILURE_LOGGED = False


def _log_rerank_failure(exc: Exception) -> None:
    global _RERANK_FAILURE_LOGGED
    detail = getattr(exc, "detail", None) or str(exc)
    if not _RERANK_FAILURE_LOGGED:
        _RERANK_FAILURE_LOGGED = True
        logger.error(
            "RERANKER NOT WORKING — responses will be served in RRF order ONLY for every "
            "subsequent request until fixed. model=%s endpoint=%s (%s). "
            "Full failure on first call: %s",
            openrouter.OPENROUTER_RERANK_MODEL,
            openrouter.OPENROUTER_RERANK_ENDPOINT,
            type(exc).__name__,
            detail,
        )
    else:
        logger.warning("Reranker still failing (RRF fallback): %s", detail)


async def rerank(
    chunks: list[RetrievedChunk],
    query: str,
    top_n: int = RERANK_TOP_N,
) -> list[RetrievedChunk]:
    """Rerank fused candidates with the NIM cross-encoder.

    ``index`` in the NIM response maps to each candidate's position, so scores
    are attached back onto the same chunk objects before reordering. On any
    reranker failure we log loudly and return the candidates in RRF order.
    """
    if not chunks:
        return []
    candidates = chunks[:top_n]
    documents = [c.content for c in candidates]

    try:
        results = await openrouter.rerank(query, documents, top_n=top_n)
    except Exception as exc:  # noqa: BLE001 - reranking is advisory; never 500 the chat
        _log_rerank_failure(exc)
        return candidates

    score_by_pos = {r["index"]: r["relevance_score"] for r in results}
    for pos, c in enumerate(candidates):
        c.rerank_score = score_by_pos.get(pos)

    # Sort by relevance desc; None scores (missed) go last, keep RRF order among them.
    candidates.sort(key=lambda c: (c.rerank_score is None, -(c.rerank_score or 0.0)))
    for rank, c in enumerate(candidates, start=1):
        c.rerank_rank = rank
    return candidates