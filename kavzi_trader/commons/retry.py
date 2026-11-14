import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


class RetryPolicySchema(BaseModel):
    """How often and how long to wait when retrying an async operation."""

    attempts: Annotated[int, Field(ge=1)]
    backoff_base_s: Annotated[float, Field(ge=0)]
    retry_on: tuple[type[BaseException], ...]
    strategy: Literal["linear", "exponential"] = "exponential"
    max_delay_s: Annotated[float | None, Field(gt=0)] = None

    model_config = ConfigDict(frozen=True)

    def delay_s(self, attempt: int) -> float:
        """Delay after the 1-based ``attempt`` failed."""
        if self.strategy == "linear":
            delay = self.backoff_base_s * attempt
        else:
            delay = self.backoff_base_s * 2 ** (attempt - 1)
        if self.max_delay_s is not None:
            delay = min(delay, self.max_delay_s)
        return delay


async def retry_async[TResult](
    operation: Callable[[], Awaitable[TResult]],
    policy: RetryPolicySchema,
    *,
    name: str,
    before_retry: Callable[[], Awaitable[None]] | None = None,
) -> TResult:
    """Run ``operation``, retrying on ``policy.retry_on`` errors.

    Other exceptions propagate immediately; after the last attempt the final
    retryable error is re-raised. ``before_retry`` runs after the backoff sleep.
    """
    for attempt in range(1, policy.attempts + 1):
        try:
            return await operation()
        except policy.retry_on as exc:
            if attempt == policy.attempts:
                raise
            delay_s = policy.delay_s(attempt)
            logger.warning(
                "%s attempt %d/%d failed: %s; retrying in %.1fs",
                name,
                attempt,
                policy.attempts,
                exc,
                delay_s,
                extra={"attempt": attempt, "max_attempts": policy.attempts},
            )
            await asyncio.sleep(delay_s)
            if before_retry is not None:
                await before_retry()
    msg = "unreachable: retry loop exits via return or raise"
    raise AssertionError(msg)
