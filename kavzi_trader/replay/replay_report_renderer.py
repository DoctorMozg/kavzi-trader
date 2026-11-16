from kavzi_trader.evals.markdown_format import Md
from kavzi_trader.evals.trend_stats_schema import TrendStatsSchema
from kavzi_trader.replay.replay_llm_usage_schema import ReplayLlmUsageSchema
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
            f"archived {result.interval} bars: {', '.join(result.symbols)}; "
            f"{first} to {last}. "
            f"Equity {result.initial_equity:.2f} -> {result.final_equity:.2f} USDT, "
            f"funding received {result.funding_received:.2f} USDT."
        )
        blocks = ["# Strategy replay"]
        if result.llm is not None and result.llm.contaminated:
            blocks.append(
                "> **Contaminated diagnostic.** The window starts before the "
                "training cutoff of a model it asked, so the model may have "
                "seen how these days played out. Not a headline result."
            )
        blocks += [
            intro,
            self._summary(result.stats, reference),
            self._decisions(result),
        ]
        if result.llm is not None:
            blocks.append(self._llm(result.llm))
        return "\n\n".join(blocks) + "\n"

    def _summary(
        self, stats: TrendStatsSchema, reference: TrendStatsSchema | None
    ) -> str:
        labels = ["Return (annualised)", "Volatility", "Sharpe", "Max drawdown"]
        ours = self._column(stats)
        if reference is None:
            rows = [list(r) for r in zip(labels, ours, strict=True)]
            return Md.section("Summary", Md.table(["", "Replay"], rows))
        theirs = self._column(reference)
        rows = [list(r) for r in zip(labels, ours, theirs, strict=True)]
        note = (
            "The vectorized rule holds constant weights and pays fees on weight "
            "changes; the replay holds quantities between rebalances, rounds to "
            "lots and passes every intent through the live risk checks."
        )
        table = Md.table(["", "Replay", "Vectorized rule"], rows)
        return Md.section("Summary", table, note)

    def _decisions(self, result: ReplayResultSchema) -> str:
        text = (
            f"Orders placed: {result.orders}. "
            f"Intents that failed in execution: {result.failed_decisions}."
        )
        if not result.rejections:
            return Md.section("Intents", text)
        rows = [[reason, str(n)] for reason, n in result.rejections.items()]
        table = Md.table(["Rejected because", "Intents"], rows)
        return Md.section("Intents", text, table)

    def _llm(self, llm: ReplayLlmUsageSchema) -> str:
        return Md.section(
            "LLM",
            f"Models: {', '.join(llm.models)}. Provider calls: "
            f"{llm.provider_calls}. Requests missing from the tape: "
            f"{llm.tape_misses}.",
        )

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
