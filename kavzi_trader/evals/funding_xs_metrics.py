from datetime import UTC, datetime

import numpy as np

from kavzi_trader.evals.funding_xs_run_schema import FundingXsRunSchema
from kavzi_trader.evals.funding_xs_summary_schema import FundingXsSummarySchema

_DAYS_PER_YEAR = 365
_MS_PER_S = 1000
_MIN_SHARPE = 0.5
_MIN_POSITIVE_YEARS = 3


class FundingXsMetrics:
    """Turns daily marks into the numbers the pre-registration reports."""

    @staticmethod
    def summarize(run: FundingXsRunSchema) -> FundingXsSummarySchema:
        days = run.days
        if len(days) < 2:
            msg = f"need at least 2 daily marks, got {len(days)}"
            raise ValueError(msg)
        returns = np.array([d.net_return for d in days])
        equity = np.array([1.0, *(d.equity for d in days)])
        years = len(days) / _DAYS_PER_YEAR
        vol = float(returns.std(ddof=1))
        yearly: dict[int, float] = {}
        for day in days:
            year = datetime.fromtimestamp(day.day_ms / _MS_PER_S, UTC).year
            yearly[year] = (yearly.get(year, 1.0) * (1.0 + day.net_return)) 
        return FundingXsSummarySchema(
            days=len(days),
            annual_return=float(equity[-1] ** (1.0 / years) - 1.0),
            annual_volatility=vol * np.sqrt(_DAYS_PER_YEAR),
            sharpe=None
            if vol == 0
            else float(returns.mean() / vol * np.sqrt(_DAYS_PER_YEAR)),
            max_drawdown=float((equity / np.maximum.accumulate(equity) - 1.0).min()),
            annual_turnover=run.turnover / years,
            annual_price_return=sum(d.price_return for d in days) / years,
            annual_funding_return=sum(d.funding_return for d in days) / years,
            annual_cost_return=sum(d.cost_return for d in days) / years,
            yearly_return={y: v - 1.0 for y, v in sorted(yearly.items())},
        )

    @staticmethod
    def passes(net: FundingXsSummarySchema) -> bool:
        """The pre-registered PASS rule, applied to the net summary."""
        positive_years = sum(r > 0 for r in net.yearly_return.values())
        return (
            net.sharpe is not None
            and net.sharpe >= _MIN_SHARPE
            and net.annual_return > 0
            and positive_years >= _MIN_POSITIVE_YEARS
        )
