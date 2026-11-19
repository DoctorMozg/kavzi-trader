from kavzi_trader.evals.markdown_format import NA, Md
from kavzi_trader.evals.trend_result_schema import TrendResultSchema
from kavzi_trader.evals.trend_stats_schema import TrendStatsSchema

PASS_SHARPE = 0.5
BOTH_UNIVERSES = "The preregistered decision needs both universes to pass."


class TrendReportRenderer:
    """Markdown report of one trend backtest, with the preregistered criterion."""

    def __init__(
        self, rule: str, preregistration: str, decision_note: str = BOTH_UNIVERSES
    ) -> None:
        self._rule = rule
        self._preregistration = preregistration
        self._decision_note = decision_note

    def render(self, result: TrendResultSchema) -> str:
        intro = (
            f"{self._rule}, {', '.join(result.symbols)}; {result.first_day} to "
            f"{result.last_day} ({result.days} days). Rules: "
            f"evals/preregistrations/{self._preregistration}."
        )
        blocks = ["# Daily weight backtest", intro, *self.sections(result)]
        return "\n\n".join(blocks) + "\n"

    def sections(self, result: TrendResultSchema) -> list[str]:
        """Summary, per-year Sharpe and criterion, for reports that embed them."""
        return [self._summary(result), self._years(result), self._criterion(result)]

    def criterion_met(self, result: TrendResultSchema) -> bool:
        sharpe = result.net.sharpe
        bench = result.benchmark.sharpe
        if sharpe is None or bench is None:
            return False
        return sharpe >= PASS_SHARPE and sharpe > bench

    def _summary(self, result: TrendResultSchema) -> str:
        net, bench = result.net, result.benchmark
        rows = [
            [
                "Net return (annualised)",
                self._pct(net.annual_return),
                self._pct(bench.annual_return),
            ],
            ["Volatility", self._pct(net.annual_vol), self._pct(bench.annual_vol)],
            ["Sharpe", Md.num(net.sharpe), Md.num(bench.sharpe)],
            [
                "Sharpe over cash",
                Md.num(net.sharpe_over_cash),
                Md.num(bench.sharpe_over_cash),
            ],
            [
                "Max drawdown",
                self._pct(net.max_drawdown),
                self._pct(bench.max_drawdown),
            ],
            ["Turnover per year (x NAV)", Md.num(result.turnover_per_year), "0"],
            ["Cost drag per year", self._pct(result.cost_drag), "0"],
            ["Funding drag per year", self._pct(result.funding_drag), "0"],
        ]
        cash = (
            f"Cash (3-month US T-bill, `evals/cash/tb3ms_monthly.csv`) paid "
            f"{self._pct(result.cash_return)} a year over the same days. Sharpe over "
            "cash scores the return above that rate."
        )
        return Md.section(
            "Summary", Md.table(["", "Strategy", "Benchmark"], rows), cash
        )

    def _years(self, result: TrendResultSchema) -> str:
        years = sorted(result.net.sharpe_by_year)
        rows = [
            [str(year), *self._year_row(result.net, result.benchmark, year)]
            for year in years
        ]
        return Md.section(
            "Sharpe per calendar year",
            Md.table(["Year", "Strategy", "Benchmark"], rows),
        )

    def _criterion(self, result: TrendResultSchema) -> str:
        verdict = "PASS" if self.criterion_met(result) else "FAIL"
        text = (
            f"Universe criterion (net Sharpe >= {PASS_SHARPE} and above the "
            f"benchmark): **{verdict}**. {self._decision_note}"
        )
        return Md.section("Criterion", text)

    @staticmethod
    def _year_row(
        net: TrendStatsSchema, bench: TrendStatsSchema, year: int
    ) -> list[str]:
        return [
            Md.num(net.sharpe_by_year[year]),
            Md.num(bench.sharpe_by_year.get(year)),
        ]

    @staticmethod
    def _pct(value: float | None) -> str:
        return NA if value is None else f"{100 * value:.1f}%"
