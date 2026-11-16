from kavzi_trader.evals.markdown_format import NA, Md
from kavzi_trader.evals.trend_result_schema import TrendResultSchema
from kavzi_trader.evals.trend_stats_schema import TrendStatsSchema
from kavzi_trader.strategies.trend.trend_params_schema import TrendParamsSchema

PASS_SHARPE = 0.5


class TrendReportRenderer:
    """Markdown report of one trend backtest, with the preregistered criterion."""

    def __init__(self, params: TrendParamsSchema) -> None:
        self._params = params

    def render(self, result: TrendResultSchema) -> str:
        variant = "long/short" if self._params.long_short else "long/flat"
        intro = (
            f"Donchian ensemble {variant}, lookbacks {list(self._params.lookbacks)}, "
            f"{', '.join(result.symbols)}; {result.first_day} to {result.last_day} "
            f"({result.days} days). Rules: "
            "evals/preregistrations/2026_11_16_trend_following.md."
        )
        blocks = [
            "# Trend following backtest",
            intro,
            self._summary(result),
            self._years(result),
            self._criterion(result),
        ]
        return "\n\n".join(blocks) + "\n"

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
                "Max drawdown",
                self._pct(net.max_drawdown),
                self._pct(bench.max_drawdown),
            ],
            ["Turnover per year (x NAV)", Md.num(result.turnover_per_year), "0"],
            ["Cost drag per year", self._pct(result.cost_drag), "0"],
            ["Funding drag per year", self._pct(result.funding_drag), "0"],
        ]
        return Md.section("Summary", Md.table(["", "Strategy", "Benchmark"], rows))

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
            f"benchmark): **{verdict}**. The preregistered decision needs both "
            "universes to pass."
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
