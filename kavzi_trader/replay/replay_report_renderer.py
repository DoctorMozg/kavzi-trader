from kavzi_trader.evals.markdown_format import NA, Md
from kavzi_trader.evals.trend_stats_schema import TrendStatsSchema
from kavzi_trader.replay.replay_result_schema import ReplayResultSchema


class ReplayReportRenderer:
    """Markdown report of one replay, beside the vectorized rule when given."""

    def render(
        self, result: ReplayResultSchema, reference: TrendStatsSchema | None
    ) -> str:
        first = result.equity.index[1].date().isoformat()
        last = result.equity.index[-1].date().isoformat()
        intro = (
            f"Strategy `{result.strategy}` replayed through the live spine on "
            f"cached 4h bars: {', '.join(result.symbols)}; {first} to {last}. "
            f"Equity {result.initial_equity:.2f} -> {result.final_equity:.2f} USDT, "
            f"funding received {result.funding_received:.2f} USDT."
        )
        blocks = [
            "# Strategy replay",
            intro,
            self._summary(result.stats, reference),
            self._decisions(result),
        ]
        return "\n\n".join(blocks) + "\n"

    def _summary(
        self, stats: TrendStatsSchema, reference: TrendStatsSchema | None
    ) -> str:
        labels = ["Return (annualised)", "Volatility", "Sharpe", "Max drawdown"]
        ours = self._column(stats)
        theirs = self._column(reference) if reference else [NA] * len(labels)
        rows = [list(r) for r in zip(labels, ours, theirs, strict=True)]
        note = (
            "The vectorized rule holds constant weights and pays fees on weight "
            "changes; the replay holds quantities between rebalances, rounds to "
            "lots and passes every intent through the live risk checks."
        )
        table = Md.table(["", "Replay", "Vectorized rule"], rows)
        return Md.section("Summary", table, note)

    def _decisions(self, result: ReplayResultSchema) -> str:
        text = f"Orders placed: {result.orders}."
        if not result.rejections:
            return Md.section("Intents", text)
        rows = [[reason, str(n)] for reason, n in result.rejections.items()]
        table = Md.table(["Rejected because", "Intents"], rows)
        return Md.section("Intents", text, table)

    def _column(self, stats: TrendStatsSchema) -> list[str]:
        return [
            self._pct(stats.annual_return),
            self._pct(stats.annual_vol),
            Md.num(stats.sharpe),
            self._pct(stats.max_drawdown),
        ]

    @staticmethod
    def _pct(value: float) -> str:
        return f"{100 * value:.1f}%"
