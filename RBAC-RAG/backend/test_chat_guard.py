"""Tests for nim_client.chat() reasoning-leak protection.

Reasoning chat models (nemotron-3.x) can exhaust max_tokens mid-chain-of-
thought; NIM then returns finish_reason="length" with the PARTIAL REASONING in
message.content. chat() must never surface that text: it retries with a larger
budget and fails cleanly instead. These tests patch the transport layer only -
no live network.
"""
import asyncio
from unittest.mock import patch

import pytest
from fastapi import HTTPException

import nim_client


def run(coro):
    return asyncio.run(coro)


def _resp(content, finish):
    return {"choices": [{"message": {"content": content, "reasoning_content": None},
                         "finish_reason": finish}]}


def test_chat_returns_clean_content_on_stop():
    captured = []

    async def fake_request(method, url, *, json_body, **kw):
        captured.append(json_body)
        return _resp("PARIS IS THE ANSWER", "stop")

    with patch("nim_client._request_with_retry", side_effect=fake_request):
        out = run(nim_client.chat("sys", "user", max_tokens=700))

    assert out == "PARIS IS THE ANSWER"
    assert len(captured) == 1
    # Thinking disabled by default: no output budget wasted on chain-of-thought.
    assert captured[0]["chat_template_kwargs"] == {"thinking": False}


def test_chat_retries_larger_budget_and_never_returns_partial_reasoning():
    """First response is truncated mid-reasoning (length) -> retry with 2x budget
    -> clean stop. The partial reasoning text must never be returned."""
    bodies = []

    async def fake_request(method, url, *, json_body, **kw):
        bodies.append(json_body)
        if json_body["max_tokens"] <= 700:
            return _resp("Here's a thinking process:\n1. Analyze the question...", "length")
        return _resp("FINAL CLEAN ANSWER", "stop")

    with patch("nim_client._request_with_retry", side_effect=fake_request):
        out = run(nim_client.chat("sys", "user", max_tokens=700))

    assert out == "FINAL CLEAN ANSWER"
    assert "thinking process" not in out
    assert [b["max_tokens"] for b in bodies] == [700, 1400]


def test_chat_persistently_truncated_fails_cleanly():
    """Never-completing responses must raise a clean 502 - the raw (possibly
    reasoning) content is NEVER returned to callers."""
    async def fake_request(method, url, *, json_body, **kw):
        return _resp("Here's a thinking process:\n1. ...", "length")

    with patch("nim_client._request_with_retry", side_effect=fake_request):
        with pytest.raises(HTTPException) as exc:
            run(nim_client.chat("sys", "user", max_tokens=700))
    assert exc.value.status_code == 502
    assert "thinking" not in exc.value.detail.lower()


def test_chat_stop_with_empty_content_fails_cleanly():
    async def fake_request(method, url, *, json_body, **kw):
        return _resp("", "stop")

    with patch("nim_client._request_with_retry", side_effect=fake_request):
        with pytest.raises(HTTPException) as exc:
            run(nim_client.chat("sys", "user", max_tokens=700))
    assert exc.value.status_code == 502