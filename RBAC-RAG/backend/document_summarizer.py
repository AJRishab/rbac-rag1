"""Document-summary stage: bounded hierarchical (map-reduce) summarization.

Takes the FULL, RBAC-verified chunk list of ONE resolved document and produces
a single coherent document-level summary. Chunks are processed strictly in
document order and grouped into context-bounded batches; each batch gets a
map-summary, then map summaries are combined/reduced recursively until they
fit, then a final coherent summary is produced.

Everything here runs AFTER the router resolved an authorized document and
retrieved its chunks with RBAC enforced inside SQL (see retrieval.document_chunks
+ retrieval.assert_rbac), so the summarizer itself trusts the input list.

The dedicated prompts enforce source-grounding: the only document identity is
the server-provided filename; document/report names appearing inside chunk text
are content, never additional sources.
"""
import logging
import re

import tiktoken

import nim_client
from retrieval import RetrievedChunk, SECTION_WORDS, section_heading_line_re

logger = logging.getLogger(__name__)

# cl100k_base is already a project dependency (used by ingest.py for ~500-token
# chunking). It is only a conservative *budget estimator* here; the chat model's
# own tokenizer would be tighter but this keeps the pipeline dependency-free.
_ENC = tiktoken.get_encoding("cl100k_base")

# Per-batch input budget (tokens). llama-3.1-8b-instruct has 8192 context;
# leave generous room for the prompt + the ~700-token summary output.
BATCH_MAX_TOKENS = 5000
# Reduce-stage budget: combined map summaries above this get condensed.
REDUCE_MAX_TOKENS = 4000
# Safe bound on recursion depth (protects against pathological reducer loops).
MAX_REDUCE_LEVELS = 8
SUMMARY_OUT_MAX_TOKENS = 700

_SOURCE_RULES = (
    "Summarize ONLY the authorized content supplied below. Do not use outside "
    "knowledge. Do not invent facts. Do not infer or reference any other "
    "document. The selected document identity is provided below from "
    "server-side DB metadata (title/filename). A filename or publication name "
    "that appears INSIDE the supplied text is merely content the document "
    "mentions - it is never a separate source and must never be presented as "
    "a citation or another document in this knowledge base."
)


def _tokens(text: str) -> int:
    return len(_ENC.encode(text or ""))


def _doc_intro(doc: dict) -> str:
    return f"Document: {doc['title'] or doc['filename']} (filename: {doc['filename']})"


def _section_clause(section: str | None) -> str:
    return f" of the '{section}' section" if section else ""


# A standalone numbered heading opens a new section even when its title is not
# one of SECTION_WORDS ("3.1 Dataset", "V. Ablations", "2 Model Architecture").
# Section numbers are 1-2 digits (optionally dotted), so years and other long
# numbers in body text cannot falsely match; the short-line guard avoids
# matching ordinary numbered sentences inside body text.
_NUMBERED_HEADING_RE = re.compile(
    r"^\s*(?:\d{1,2}(?:\.\d{1,2})*|[IVXLC]{1,5})[\.\)]?\s+\S",
    re.IGNORECASE,
)
_HEADING_MAX_LINE_LEN = 80


def _starts_new_section(content: str, current: str) -> bool:
    """True if `content` contains a standalone heading line opening a section
    other than `current` (another known section word, or a numbered heading)."""
    for raw in content.splitlines():
        line = raw.strip()
        if not line or len(line) > _HEADING_MAX_LINE_LEN:
            continue
        for word in SECTION_WORDS:
            if word != current and section_heading_line_re(word).match(line):
                return True
        if _NUMBERED_HEADING_RE.match(line):
            return True
    return False


def select_section_chunks(chunks: list[RetrievedChunk], section: str | None) -> list[RetrievedChunk] | None:
    """Contiguous, document-order run of chunks belonging to a named section.

    The section STARTS at the first chunk containing a standalone heading line
    for `section` ("Abstract", "1. Introduction", "II. RELATED WORK") and ENDS
    before the next chunk that opens a different section. Chunks are never
    split and order is preserved, so the section summary follows the document.

    The input MUST already be the RBAC-verified chunk list (selection only
    narrows it, never widens it). Returns ``None`` when no chunk contains the
    section heading so the caller can fall back to the whole-document summary
    instead of guessing.
    """
    if not chunks or not section:
        return None
    start_re = section_heading_line_re(section)
    start = None
    for i, c in enumerate(chunks):
        if any(start_re.match(line.strip()) for line in (c.content or "").splitlines()):
            start = i
            break
    if start is None:
        return None
    selected = [chunks[start]]
    for c in chunks[start + 1:]:
        if _starts_new_section(c.content or "", section):
            break
        selected.append(c)
    return selected


def _format_chunks(chunks: list[RetrievedChunk], filename: str) -> str:
    """Render a contiguous batch using the existing [Source #N ...] header style."""
    return "\n\n".join(
        f"[Source #{i + 1}: {filename}; page {c.page or 'unknown'}; chunk {c.id}]\n{c.content}"
        for i, c in enumerate(chunks)
    )


def _group_chunks(chunks: list[RetrievedChunk], target_tokens: int = BATCH_MAX_TOKENS) -> list[list[RetrievedChunk]]:
    """Contiguous, document-order grouping of chunks into bounded batches.

    A single chunk larger than the budget goes in its own batch (never split).
    Order is preserved exactly, so the summary follows document order.
    """
    groups: list[list[RetrievedChunk]] = []
    current: list[RetrievedChunk] = []
    total = 0
    for c in chunks:
        cost = _tokens(c.content) + 96  # header overhead (filename, id, page)
        if current and total + cost > target_tokens:
            groups.append(current)
            current, total = [c], cost
        else:
            current.append(c)
            total += cost
    if current:
        groups.append(current)
    return groups


def _group_texts(texts: list[str], target_tokens: int = REDUCE_MAX_TOKENS) -> list[list[str]]:
    """Contiguous grouping of summary texts for the reduce pass."""
    groups: list[list[str]] = []
    current: list[str] = []
    total = 0
    for t in texts:
        cost = _tokens(t)
        if current and total + cost > target_tokens:
            groups.append(current)
            current, total = [t], cost
        else:
            current.append(t)
            total += cost
    if current:
        groups.append(current)
    return groups


async def _call_map(batch_text: str, doc: dict, section: str | None = None) -> str:
    system = (
        "You are SENTRY/RAG, producing a section summary"
        f"{_section_clause(section)} of ONE authorized document. "
        + _SOURCE_RULES
        + " Write a concise section summary covering the key points of this section. "
        "Output only the summary, no preamble. Never output your reasoning or planning."
    )
    user = f"{_doc_intro(doc)}\n\nSection content:\n{batch_text}"
    return await nim_client.chat(system, user, max_tokens=SUMMARY_OUT_MAX_TOKENS, temperature=0.2)


async def _call_reduce(group_text: str, doc: dict, section: str | None = None) -> str:
    system = (
        "You are SENTRY/RAG, condensing section summaries of ONE authorized document. "
        + _SOURCE_RULES
        + f" Combine the section summaries below into a tighter summary{_section_clause(section)}, "
        "keeping every key point and losing nothing important. Output only the condensed "
        "summary. Never output your reasoning or planning."
    )
    user = f"{_doc_intro(doc)}\n\nSection summaries:\n{group_text}"
    return await nim_client.chat(system, user, max_tokens=SUMMARY_OUT_MAX_TOKENS, temperature=0.2)


async def _call_final(parts: list[str], doc: dict, section: str | None = None) -> str:
    system = (
        "You are SENTRY/RAG, producing the FINAL summary of ONE authorized document. "
        + _SOURCE_RULES
        + f" Combine the section summaries below into ONE coherent summary{_section_clause(section)} "
        "(a few short paragraphs, using bullet points for key facts if that helps). "
        f"The document being summarized is '{doc['filename']}'."
        " Do not mention or imply any other document. Output only the final summary. "
        "Never output your reasoning or planning."
    )
    body = "\n\n".join(f"[Part summary {i + 1}]\n{p}" for i, p in enumerate(parts))
    user = f"{_doc_intro(doc)}\n\nSection summaries:\n{body}"
    return await nim_client.chat(system, user, max_tokens=SUMMARY_OUT_MAX_TOKENS, temperature=0.4)


async def summarize_document(
    chunks: list[RetrievedChunk],
    doc: dict,
    admin_bypass: bool = False,
    section: str | None = None,
) -> tuple[str, int, int]:
    """Summarize one authorized document (or one named section of it).

    Returns ``(summary, chunk_count, llm_calls)``. When ``section`` is given,
    ``chunks`` must already be narrowed to that section
    (:func:`select_section_chunks`) and every prompt restricts the summary to
    that section only.

    Path:
      * 0 chunks      -> caller handles "no accessible content" (never called here
                         with an empty list in practice; defensive).
      * fits one batch -> single final summary call.
      * otherwise: MAP each contiguous batch, REDUCE combined summaries until they
        fit the final context, then FINAL.
    ``llm_calls`` exposes the number of NIM calls for the retrieval_detail audit.
    """
    if not chunks:
        return "", 0, 0

    batches = _group_chunks(chunks)
    total_calls = 0
    if len(batches) == 1:
        text = _format_chunks(batches[0], doc["filename"])
        out = await _call_final_group(text, doc, section)
        return out, len(chunks), 1

    parts: list[str] = []
    for b in batches:
        parts.append(await _call_map(_format_chunks(b, doc["filename"]), doc, section))
        total_calls += 1

    levels = 1
    while (
        len(parts) > 1
        and sum(_tokens(p) for p in parts) > REDUCE_MAX_TOKENS
        and levels < MAX_REDUCE_LEVELS
    ):
        new_parts: list[str] = []
        for g in _group_texts(parts):
            if len(g) == 1:
                new_parts.append(g[0])  # single summary: pass through unchanged
            else:
                new_parts.append(await _call_reduce("\n\n".join(g), doc, section))
                total_calls += 1
        parts = new_parts
        levels += 1

    out = await _call_final(parts, doc, section)
    total_calls += 1
    return out, len(chunks), total_calls


async def _call_final_group(text: str, doc: dict, section: str | None = None) -> str:
    """Final summary for a document (or section) that fits a single batch."""
    system = (
        "You are SENTRY/RAG, producing a summary"
        f"{_section_clause(section)} of ONE authorized document. "
        + _SOURCE_RULES
        + " Write ONE coherent summary (a few short paragraphs; use "
        "bullet points for key facts if that helps). "
        f"The document being summarized is '{doc['filename']}'."
        " Do not mention or imply any other document. Output only the summary. "
        "Never output your reasoning or planning."
    )
    user = f"{_doc_intro(doc)}\n\nDocument content:\n{text}"
    return await nim_client.chat(system, user, max_tokens=SUMMARY_OUT_MAX_TOKENS, temperature=0.4)
