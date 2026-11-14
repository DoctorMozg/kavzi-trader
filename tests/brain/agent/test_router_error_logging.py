"""Unit tests for the LLM-failure log dispatcher in router.py.

Errors are produced by a real pydantic-ai agent over a mock transport, so the
tests cover the exception types production actually sees.
"""

import logging
from collections.abc import Callable

import httpx2
import pytest
from openai import AsyncOpenAI
from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from kavzi_trader.brain.agent.llm_error_logging import log_llm_exception

Handler = Callable[[httpx2.Request], httpx2.Response]


class _OutputSchema(BaseModel):
    value: int


async def _raise_from_agent(handler: Handler) -> Exception:
    client = AsyncOpenAI(
        base_url="https://openrouter.test/api/v1",
        api_key="test",
        max_retries=0,
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)),
    )
    model = OpenAIChatModel("test-model", provider=OpenAIProvider(openai_client=client))
    agent = Agent(model, output_type=_OutputSchema)
    with pytest.raises(Exception) as exc_info:
        await agent.run("hi")
    raised: Exception = exc_info.value
    return raised


def _status_handler(status_code: int, retry_after: str | None = None) -> Handler:
    headers = {"retry-after": retry_after} if retry_after is not None else {}

    def handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            status_code, json={"error": {"message": "nope"}}, headers=headers
        )

    return handler


def _timeout_handler(request: httpx2.Request) -> httpx2.Response:
    raise httpx2.ReadTimeout("timed out", request=request)


def _log(exc: BaseException, symbol: str = "BTCUSDT", agent: str = "analyst") -> None:
    log_llm_exception(
        symbol,
        agent,
        exc,
        elapsed_ms=1234.5,
        body_preview_chars=500,
        exc_message_preview_chars=200,
    )


async def test_server_error_logs_status_code(
    caplog: pytest.LogCaptureFixture,
) -> None:
    exc = await _raise_from_agent(_status_handler(502, retry_after="30"))

    with caplog.at_level(logging.WARNING):
        _log(exc)

    matching = [r for r in caplog.records if "HTTP 502" in r.message]
    assert len(matching) == 1
    record = matching[0]
    assert record.http_status == 502
    assert record.retry_after == 30.0
    assert record.symbol == "BTCUSDT"
    assert record.agent == "analyst"
    assert record.elapsed_ms == 1234.5


async def test_rate_limit_logs_retry_after(
    caplog: pytest.LogCaptureFixture,
) -> None:
    exc = await _raise_from_agent(_status_handler(429, retry_after="60"))

    with caplog.at_level(logging.WARNING):
        _log(exc, symbol="ETHUSDT")

    matching = [r for r in caplog.records if "rate-limited" in r.message]
    assert len(matching) == 1
    record = matching[0]
    assert record.http_status == 429
    assert record.retry_after == 60.0
    assert record.symbol == "ETHUSDT"


async def test_transport_timeout_logged_as_timeout(
    caplog: pytest.LogCaptureFixture,
) -> None:
    exc = await _raise_from_agent(_timeout_handler)

    with caplog.at_level(logging.WARNING):
        _log(exc, symbol="BNBUSDT", agent="trader")

    matching = [r for r in caplog.records if "LLM timed out" in r.message]
    assert len(matching) == 1
    assert matching[0].elapsed_ms == 1234.5


def test_builtin_timeout_error_logged_as_timeout(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Python's builtin TimeoutError must be routed to the timeout branch,
    # not the generic fallback, so operators can set one dashboard filter.
    exc = TimeoutError("builtin timeout")

    with caplog.at_level(logging.WARNING):
        log_llm_exception(
            "XRPUSDT",
            "analyst",
            exc,
            elapsed_ms=1000.0,
            body_preview_chars=500,
            exc_message_preview_chars=200,
        )

    matching = [r for r in caplog.records if "timed out" in r.message]
    assert len(matching) == 1
    assert matching[0].exception_type == "TimeoutError"


def test_unexpected_model_body_preview_in_message(
    caplog: pytest.LogCaptureFixture,
) -> None:
    long_body = "x" * 2000
    exc = UnexpectedModelBehavior("parse failed", body=long_body)

    with caplog.at_level(logging.WARNING):
        log_llm_exception(
            "ADAUSDT",
            "trader",
            exc,
            elapsed_ms=2500.0,
            body_preview_chars=500,
            exc_message_preview_chars=200,
        )

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
        log_llm_exception(
            "LINKUSDT",
            "trader",
            exc,
            elapsed_ms=100.0,
            body_preview_chars=500,
            exc_message_preview_chars=200,
        )

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
        log_llm_exception(
            "AVAXUSDT",
            "analyst",
            exc,
            elapsed_ms=50.0,
            body_preview_chars=500,
            exc_message_preview_chars=200,
        )

    matching = [r for r in caplog.records if "LLM failed" in r.message]
    assert len(matching) == 1
    record = matching[0]
    assert record.exception_type == "RuntimeError"
    # First 200 chars of the original message appear in the log line.
    assert message[:200] in record.message
    # But the full 1500-char message is not dumped.
    assert message[:250] not in record.message
