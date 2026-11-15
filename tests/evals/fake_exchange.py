from kavzi_trader.api.binance.schemas.data_dicts import (
    FundingRateDict,
    OpenInterestHistDict,
)

SETTLE_MS = 8 * 3600 * 1000
OI_STEP_MS = 15 * 60 * 1000


def settlement_rate(ms: int) -> float:
    return 0.0001 * (1 + (ms // SETTLE_MS) % 5)


def open_interest(ms: int) -> float:
    return 1000.0 + (ms // OI_STEP_MS) % 7


class FakeExchange:
    """Serves 8h funding and 15m OI histories in pages, like Binance does.

    As on Binance, OI without an end time returns the latest rows.
    """

    def __init__(self, now_ms: int) -> None:
        self.now_ms = now_ms
        self.funding_calls: list[tuple[int, int, int]] = []
        self.oi_calls: list[tuple[int, int | None, int]] = []

    async def get_funding_rate(
        self, symbol: str, limit: int, start_time: int, end_time: int
    ) -> list[FundingRateDict]:
        self.funding_calls.append((start_time, end_time, limit))
        first = start_time + (-start_time) % SETTLE_MS
        times = list(range(first, end_time + 1, SETTLE_MS))[:limit]
        return [
            FundingRateDict(
                symbol=symbol, fundingRate=str(settlement_rate(t)), fundingTime=t
            )
            for t in times
        ]

    async def get_open_interest_history(
        self,
        symbol: str,
        period: str,
        limit: int,
        start_time: int,
        end_time: int | None = None,
    ) -> list[OpenInterestHistDict]:
        self.oi_calls.append((start_time, end_time, limit))
        first = start_time + (-start_time) % OI_STEP_MS
        last = min(self.now_ms, self.now_ms if end_time is None else end_time)
        times = list(range(first, last + 1, OI_STEP_MS))
        times = times[-limit:] if end_time is None else times[:limit]
        return [
            OpenInterestHistDict(
                symbol=symbol,
                sumOpenInterest=str(open_interest(t)),
                sumOpenInterestValue="0",
                timestamp=t,
            )
            for t in times
        ]
