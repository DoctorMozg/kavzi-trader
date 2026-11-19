from kavzi_trader.evals.markdown_format import Md
from kavzi_trader.evals.trend_result_schema import TrendResultSchema
from kavzi_trader.evals.validation.paired_sharpe_schema import PairedSharpeSchema


def _pct(value: float) -> str:
    return f"{100 * value:.1f}%"


class AblationReportRenderer:
    """Markdown report of one arm against the base rule over the same days."""

    def __init__(self, base: str, arm: str, preregistration: str | None) -> None:
        self._base = base
        self._arm = arm
        self._prereg = preregistration

    def render(
        self,
        base: TrendResultSchema,
        arm: TrendResultSchema,
        paired: PairedSharpeSchema,
    ) -> str:
        rules = (
            f"Rules: evals/preregistrations/{self._prereg}."
            if self._prereg
            else "Exploratory: no preregistration decides on this run."
        )
        intro = (
            f"Base: {self._base}. Arm: {self._arm}. {len(base.symbols)} symbols; "
            f"{base.first_day} to {base.last_day} ({base.days} days). {rules}"
        )
        blocks = ["# Trend ablation", intro, *self.sections(base, arm, paired)]
        return "\n\n".join(blocks) + "\n"

    @staticmethod
    def sections(
        base: TrendResultSchema,
        arm: TrendResultSchema,
        paired: PairedSharpeSchema,
    ) -> list[str]:
        """Summary, paired test and per-year Sharpe, for reports that embed them."""
        rows = [
            ["Net Sharpe", Md.num(base.net.sharpe), Md.num(arm.net.sharpe)],
            [
                "Sharpe over cash",
                Md.num(base.net.sharpe_over_cash),
                Md.num(arm.net.sharpe_over_cash),
            ],
            [
                "Net return (annualised)",
                _pct(base.net.annual_return),
                _pct(arm.net.annual_return),
            ],
            ["Volatility", _pct(base.net.annual_vol), _pct(arm.net.annual_vol)],
            ["Max drawdown", _pct(base.net.max_drawdown), _pct(arm.net.max_drawdown)],
            [
                "Turnover per year (x NAV)",
                Md.num(base.turnover_per_year),
                Md.num(arm.turnover_per_year),
            ],
            ["Cost drag per year", _pct(base.cost_drag), _pct(arm.cost_drag)],
            ["Funding drag per year", _pct(base.funding_drag), _pct(arm.funding_drag)],
        ]
        years = sorted(base.net.sharpe_by_year)
        year_rows = [
            [
                str(y),
                Md.num(base.net.sharpe_by_year[y]),
                Md.num(arm.net.sharpe_by_year.get(y)),
            ]
            for y in years
        ]
        paired_text = (
            f"Sharpe difference (arm - base): {paired.difference:+.3f}, 90% interval "
            f"[{paired.lower:+.3f}, {paired.upper:+.3f}], share of resamples where "
            f"the arm is not better: {paired.p_not_better:.3f} "
            f"({paired.resamples} stationary-bootstrap resamples, mean block "
            f"{paired.mean_block_days} days)."
        )
        return [
            Md.section("Summary", Md.table(["", "Base", "Arm"], rows)),
            Md.section("Paired comparison", paired_text),
            Md.section("Sharpe by year", Md.table(["Year", "Base", "Arm"], year_rows)),
        ]
