import logging

from pydantic_ai.exceptions import (
    ModelHTTPError,
    ModelRateLimitError,
    UnexpectedModelBehavior,
)

from kavzi_trader.brain.agent.llm_errors import LLM_TIMEOUT_ERRORS

logger = logging.getLogger(__name__)


def log_llm_exception(
    symbol: str,
    agent: str,
    exc: BaseException,
    elapsed_ms: float,
    *,
    body_preview_chars: int,
    exc_message_preview_chars: int,
) -> None:
    """Structured log dispatcher for Analyst / Trader LLM failures.

    Branches by exception type so operators can separate rate limits,
    timeouts, schema-retry exhaustion, and generic failures from the log
    stream without parsing tracebacks.
    """
    base_extra: dict[str, object] = {
        "symbol": symbol,
        "agent": agent,
        "exception_type": type(exc).__name__,
        "elapsed_ms": round(elapsed_ms, 1),
    }
    if isinstance(exc, ModelRateLimitError):
        extra = base_extra | {"http_status": 429, "retry_after": exc.retry_after}
        logger.warning(
            "%s LLM rate-limited for %s after %.1fms (retry_after=%s): %s",
            agent,
            symbol,
            elapsed_ms,
            exc.retry_after,
            str(exc)[:exc_message_preview_chars],
            extra=extra,
        )
        return
    if isinstance(exc, ModelHTTPError):
        extra = base_extra | {
            "http_status": exc.status_code,
            "retry_after": exc.retry_after,
        }
        logger.warning(
            "%s LLM HTTP %s for %s after %.1fms (retry_after=%s): %s",
            agent,
            exc.status_code,
            symbol,
            elapsed_ms,
            exc.retry_after,
            str(exc)[:exc_message_preview_chars],
            extra=extra,
        )
        return
    if isinstance(exc, LLM_TIMEOUT_ERRORS):
        logger.warning(
            "%s LLM timed out for %s after %.1fms (type=%s)",
            agent,
            symbol,
            elapsed_ms,
            type(exc).__name__,
            extra=base_extra,
        )
        return
    if isinstance(exc, UnexpectedModelBehavior):
        body_preview = str(exc.body or "")[:body_preview_chars]
        extra = base_extra | {"raw_body": exc.body, "body_preview": body_preview}
        logger.warning(
            "%s LLM unparseable output for %s after %.1fms: %s | body_preview=%s",
            agent,
            symbol,
            elapsed_ms,
            exc.message,
            body_preview,
            extra=extra,
        )
        return
    logger.error(
        "%s LLM failed for %s after %.1fms (type=%s): %s",
        agent,
        symbol,
        elapsed_ms,
        type(exc).__name__,
        str(exc)[:exc_message_preview_chars],
        exc_info=exc,
        extra=base_extra,
    )
