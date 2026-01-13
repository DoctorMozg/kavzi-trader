from decimal import Decimal

import pandas as pd

from kavzi_trader.order_flow.schemas import FundingAnalysisSchema, FundingRateSchema

DEFAULT_ZSCORE_WINDOW = 30
MIN_FUNDING_RATES_FOR_ZSCORE = 2


def calculate_funding_zscore(
    funding_rates: list[FundingRateSchema],
    window: int = DEFAULT_ZSCORE_WINDOW,
) -> FundingAnalysisSchema | None:
    if len(funding_rates) < MIN_FUNDING_RATES_FOR_ZSCORE:
        return None

    rates = [float(fr.funding_rate) for fr in funding_rates]
    series = pd.Series(rates)

    mean = series.rolling(window=min(window, len(rates)), min_periods=2).mean()
    std = series.rolling(window=min(window, len(rates)), min_periods=2).std()

    if std.iloc[-1] == 0 or pd.isna(std.iloc[-1]):
        zscore = Decimal("0")
    else:
        zscore = Decimal(str((rates[-1] - mean.iloc[-1]) / std.iloc[-1]))

    latest = funding_rates[-1]

    return FundingAnalysisSchema(
        funding_rate=latest.funding_rate,
        funding_zscore=zscore.quantize(Decimal("0.0001")),
        next_funding_time=latest.funding_time,
    )
