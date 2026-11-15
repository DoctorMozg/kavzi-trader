from kavzi_trader.evals.funding_xs_metrics import FundingXsMetrics
from kavzi_trader.evals.funding_xs_params_schema import FundingXsParamsSchema
from kavzi_trader.evals.funding_xs_run_schema import FundingXsRunSchema
from kavzi_trader.evals.funding_xs_summary_schema import FundingXsSummarySchema
from kavzi_trader.evals.markdown_format import Md

_PRIMARY = FundingXsParamsSchema()


class FundingXsReportRenderer:
    """Markdown report of one cross-sectional funding run."""

    def __init__(self, params: FundingXsParamsSchema, symbols: list[str]) -> None:
        self._params = params
        self._symbols = symbols

    def render(
        self,
        net_run: FundingXsRunSchema,
        net: FundingXsSummarySchema,
        gross: FundingXsSummarySchema,
    ) -> str:
        p = self._params
        primary = p.legs == _PRIMARY.legs and p.hold_days == _PRIMARY.hold_days
        label = "primary" if primary else "exploratory, not the pre-registered primary"
        verdict = "PASS" if FundingXsMetrics.passes(net) else "FAIL"
        intro = (
            f"Short the {p.legs} highest and long the {p.legs} lowest mean funding "
            f"(last {p.score_settlements} settlements) of {len(self._symbols)} perps "
            f"({', '.join(self._symbols)}), rebalanced every {p.hold_days} days, "
            f"cost {p.cost_rate} x |weight change| ({label}). "
            f"{net.days} daily marks, {net_run.rebalances} rebalances "
            f"({net_run.skipped_rebalances} skipped for too few scored symbols)."
        )
        blocks = [
            "# Cross-sectional funding backtest",
            intro,
            f"## Verdict: {verdict}",
            "Spec rule: net Sharpe >= 0.5, net annualised return > 0, net return "
            "> 0 in at least 3 of 5 calendar years."
            + ("" if primary else " Applies to the primary run only."),
            "## Summary",
            self._summary(net, gross),
            "## Net return by calendar year",
            Md.table(
                ["Year", "Net return"],
                [[str(y), f"{r:+.2%}"] for y, r in net.yearly_return.items()],
            ),
        ]
        return "\n\n".join(blocks) + "\n"

    @staticmethod
    def _summary(net: FundingXsSummarySchema, gross: FundingXsSummarySchema) -> str:
        pct = "{:+.2%}".format
        rows = [
            ["Annualised return", pct(net.annual_return), pct(gross.annual_return)],
            ["Volatility", pct(net.annual_volatility), pct(gross.annual_volatility)],
            ["Sharpe", Md.rate(net.sharpe), Md.rate(gross.sharpe)],
            ["Max drawdown", pct(net.max_drawdown), pct(gross.max_drawdown)],
            ["Price component (annual)", pct(net.annual_price_return),
             pct(gross.annual_price_return)],
            ["Funding component (annual)", pct(net.annual_funding_return),
             pct(gross.annual_funding_return)],
            ["Costs (annual)", pct(net.annual_cost_return),
             pct(gross.annual_cost_return)],
            ["Turnover (sum |dw| per year)", f"{net.annual_turnover:.1f}",
             f"{gross.annual_turnover:.1f}"],
        ]
        return Md.table(["Metric", "Net", "Gross"], rows)
