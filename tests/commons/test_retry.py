from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from kavzi_trader.commons import retry as retry_module
from kavzi_trader.commons.retry import RetryPolicySchema, retry_async


@pytest.fixture
def sleep_mock(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    mock = AsyncMock()
    monkeypatch.setattr(retry_module.asyncio, "sleep", mock)
    return mock


def _policy(**overrides: object) -> RetryPolicySchema:
    fields: dict[str, object] = {
        "attempts": 3,
        "backoff_base_s": 1.0,
        "retry_on": (ConnectionError,),
    }
    return RetryPolicySchema.model_validate(fields | overrides)


class _Flaky:
    def __init__(self, failures: int, exc: BaseException) -> None:
        self.calls = 0
        self._failures = failures
        self._exc = exc

    async def __call__(self) -> str:
        self.calls += 1
        if self.calls <= self._failures:
            raise self._exc
        return "ok"


class TestRetryPolicy:
    def test_exponential_delays_double(self) -> None:
        policy = _policy(strategy="exponential")
        assert [policy.delay_s(n) for n in (1, 2, 3)] == [1.0, 2.0, 4.0]

    def test_linear_delays_grow_by_base(self) -> None:
        policy = _policy(strategy="linear", backoff_base_s=0.5)
        assert [policy.delay_s(n) for n in (1, 2, 3)] == [0.5, 1.0, 1.5]

    def test_delay_is_capped(self) -> None:
        policy = _policy(max_delay_s=3.0)
        assert [policy.delay_s(n) for n in (1, 2, 3, 4)] == [1.0, 2.0, 3.0, 3.0]

    def test_zero_attempts_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _policy(attempts=0)


class TestRetryAsync:
    async def test_returns_first_success_without_sleeping(
        self, sleep_mock: AsyncMock
    ) -> None:
        op = _Flaky(0, ConnectionError())
        assert await retry_async(op, _policy(), name="op") == "ok"
        assert op.calls == 1
        sleep_mock.assert_not_awaited()

    async def test_retries_then_succeeds_with_backoff(
        self, sleep_mock: AsyncMock
    ) -> None:
        op = _Flaky(2, ConnectionError())
        assert await retry_async(op, _policy(), name="op") == "ok"
        assert op.calls == 3
        assert [c.args[0] for c in sleep_mock.await_args_list] == [1.0, 2.0]

    async def test_raises_last_error_after_exhausting_attempts(
        self, sleep_mock: AsyncMock
    ) -> None:
        op = _Flaky(10, ConnectionError("down"))
        with pytest.raises(ConnectionError, match="down"):
            await retry_async(op, _policy(attempts=3), name="op")
        assert op.calls == 3
        assert sleep_mock.await_count == 2

    async def test_non_retryable_error_propagates_immediately(
        self, sleep_mock: AsyncMock
    ) -> None:
        op = _Flaky(1, ValueError("bad"))
        with pytest.raises(ValueError, match="bad"):
            await retry_async(op, _policy(), name="op")
        assert op.calls == 1
        sleep_mock.assert_not_awaited()

    async def test_before_retry_runs_between_attempts_only(
        self, sleep_mock: AsyncMock
    ) -> None:
        hook = AsyncMock()
        op = _Flaky(3, ConnectionError())
        with pytest.raises(ConnectionError):
            await retry_async(op, _policy(attempts=3), name="op", before_retry=hook)
        assert hook.await_count == 2
