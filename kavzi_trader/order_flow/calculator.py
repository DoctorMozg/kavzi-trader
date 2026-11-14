from decimal import Decimal

from kavzi_trader.commons.time_utility import utc_now
from kavzi_trader.order_flow.funding import calculate_funding_zscore
from kavzi_trader.order_flow.open_interest import (
    calculate_oi_momentum,
    oi_period_minutes,
    periods_for_oi_period,
)
from kavzi_trader.order_flow.schemas import (
    FundingRateSchema,
    LongShortRatioSchema,
    OpenInterestSchema,
    OrderFlowSchema,
)


class OrderFlowCalculator:
    def __init__(self, interval_minutes: int = 15) -> None:
        period_minutes = oi_period_minutes(interval_minutes)
        self._periods_1h, self._periods_24h = periods_for_oi_period(period_minutes)
        self.oi_period = f"{period_minutes}m"
        # One extra sample so the 24h-ago point exists next to the current one.
        self.oi_history_limit = self._periods_24h + 1

    def calculate(
        self,
        symbol: str,
        funding_rates: list[FundingRateSchema],
        oi_history: list[OpenInterestSchema],
        long_short_ratio: LongShortRatioSchema | None = None,
        price_change_1h_percent: Decimal | None = None,
    ) -> OrderFlowSchema | None:
        funding_analysis = calculate_funding_zscore(funding_rates)
        if funding_analysis is None:
            return None

        oi_momentum = calculate_oi_momentum(
            oi_history,
            periods_1h=self._periods_1h,
            periods_24h=self._periods_24h,
        )
        if oi_momentum is None:
            return None

        return OrderFlowSchema(
            symbol=symbol,
            timestamp=utc_now(),
            funding_rate=funding_analysis.funding_rate,
            funding_zscore=funding_analysis.funding_zscore,
            next_funding_time=funding_analysis.next_funding_time,
            open_interest=oi_momentum.open_interest,
            oi_change_1h_percent=oi_momentum.oi_change_1h_percent,
            oi_change_24h_percent=oi_momentum.oi_change_24h_percent,
            long_short_ratio=long_short_ratio.long_short_ratio
            if long_short_ratio
            else None,
            long_account_percent=long_short_ratio.long_account_percent
            if long_short_ratio
            else None,
            short_account_percent=long_short_ratio.short_account_percent
            if long_short_ratio
            else None,
            price_change_1h_percent=price_change_1h_percent,
        )
