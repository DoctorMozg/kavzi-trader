"""Unit tests for the LLM-failure log dispatcher in router.py.

Covers per-type branches (httpx, openai, pydantic_ai) so operators can
distinguish rate limits, timeouts, schema-retry exhaustion, and generic
failures in the log stream.
"""

import logging

import httpx
import openai
import pytest
from pydantic_ai.exceptions import UnexpectedModelBehavior

from kavzi_trader.brain.agent.router import _log_llm_exception


def _make_httpx_response(
    status_code: int, retry_after: str | None = None
) -> httpx.Response:
    headers = {"retry-after": retry_after} if retry_after is not None else {}
    return httpx.Response(
        status_code=status_code,
        request=httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions"),
        headers=headers,
    )


def test_http_status_error_logs_status_code(
    caplog: pytest.LogCaptureFixture,
) -> None:
    response = _make_httpx_response(502, retry_after="30")
    exc = httpx.HTTPStatusError(
        "bad gateway", request=response.request, response=response
    )

    with caplog.at_level(logging.WARNING):
        _log_llm_exception("BTCUSDT", "analyst", exc, elapsed_ms=1234.5)

    matching = [r for r in caplog.records if "HTTP 502" in r.message]
    assert len(matching) == 1
    record = matching[0]
    assert record.http_status == 502
    assert record.retry_after == "30"
    assert record.symbol == "BTCUSDT"
    assert record.agent == "analyst"
    assert record.exception_type == "HTTPStatusError"
    assert record.elapsed_ms == 1234.5


def test_openai_rate_limit_logs_retry_after(
    caplog: pytest.LogCaptureFixture,
) -> None:
    response = _make_httpx_response(429, retry_after="60")
    exc = openai.RateLimitError(
        "rate limit exceeded",
        response=response,
        body=None,
    )

    with caplog.at_level(logging.WARNING):
        _log_llm_exception("ETHUSDT", "analyst", exc, elapsed_ms=500.0)

    matching = [r for r in caplog.records if "rate-limited" in r.message]
    assert len(matching) == 1
    record = matching[0]
    assert record.http_status == 429
    assert record.retry_after == "60"
    assert record.symbol == "ETHUSDT"


def test_openai_api_status_error_logs_status(
    caplog: pytest.LogCaptureFixture,
) -> None:
    response = _make_httpx_response(500)
    exc = openai.APIStatusError(
        "internal error",
        response=response,
        body={"error": {"message": "boom"}},
    )

    with caplog.at_level(logging.WARNING):
        _log_llm_exception("SOLUSDT", "trader", exc, elapsed_ms=250.0)

    matching = [r for r in caplog.records if "HTTP 500" in r.message]
    assert len(matching) == 1
    record = matching[0]
    assert record.http_status == 500
    assert record.symbol == "SOLUSDT"


def test_timeout_logs_elapsed_and_type(
    caplog: pytest.LogCaptureFixture,
) -> None:
    exc = httpx.ReadTimeout("timed out")

    with caplog.at_level(logging.WARNING):
        _log_llm_exception("BNBUSDT", "trader", exc, elapsed_ms=12_000.0)

    matching = [r for r in caplog.records if "timed out" in r.message]
    assert len(matching) == 1
    record = matching[0]
    assert record.exception_type == "ReadTimeout"
    assert record.elapsed_ms == 12000.0


def test_builtin_timeout_error_logged_as_timeout(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Python's builtin TimeoutError must be routed to the timeout branch,
    # not the generic fallback, so operators can set one dashboard filter.
    exc = TimeoutError("builtin timeout")

    with caplog.at_level(logging.WARNING):
        _log_llm_exception("XRPUSDT", "analyst", exc, elapsed_ms=1000.0)

    matching = [r for r in caplog.records if "timed out" in r.message]
    assert len(matching) == 1
    assert matching[0].exception_type == "TimeoutError"


def test_unexpected_model_body_preview_in_message(
    caplog: pytest.LogCaptureFixture,
) -> None:
    long_body = "x" * 2000
    exc = UnexpectedModelBehavior("parse failed", body=long_body)

    with caplog.at_level(logging.WARNING):
        _log_llm_exception("ADAUSDT", "trader", exc, elapsed_ms=2500.0)

    matching = [r for r in caplog.records if "unparseable output" in r.message]
    assert len(matching) == 1
    record = matching[0]
    assert record.raw_body == long_body
    assert record.body_preview == "x" * 500
    # The preview must actually appear inside the message body for text-mode
    # log handlers that ignore structured extras.
    assert ("x" * 500) in record.message
    # But the message should not include the full 2000-char body.
    assert ("x" * 501) not in record.message


def test_unexpected_model_handles_none_body(
    caplog: pytest.LogCaptureFixture,
) -> None:
    exc = UnexpectedModelBehavior("parse failed", body=None)

    with caplog.at_level(logging.WARNING):
        _log_llm_exception("LINKUSDT", "trader", exc, elapsed_ms=100.0)

    matching = [r for r in caplog.records if "unparseable output" in r.message]
    assert len(matching) == 1
    record = matching[0]
    assert record.raw_body is None
    assert record.body_preview == ""


def test_generic_exception_includes_type_and_prefix(
    caplog: pytest.LogCaptureFixture,
) -> None:
    message = "boom something " * 100  # > 200 chars, must be truncated
    exc = RuntimeError(message)

    with caplog.at_level(logging.ERROR):
        _log_llm_exception("AVAXUSDT", "analyst", exc, elapsed_ms=50.0)

    matching = [r for r in caplog.records if "LLM failed" in r.message]
    assert len(matching) == 1
    record = matching[0]
    assert record.exception_type == "RuntimeError"
    # First 200 chars of the original message appear in the log line.
    assert message[:200] in record.message
    # But the full 1500-char message is not dumped.
    assert message[:250] not in record.message
