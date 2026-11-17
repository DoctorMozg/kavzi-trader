from kavzi_trader.evals.trend_entry_schema import TrendEntrySchema
from kavzi_trader.strategies.trend.trend_gate_review_schema import (
    TrendGateReviewSchema,
)

# Part A of evals/preregistrations/2026_11_17_trend_news_gate.md.
MAX_VETOES = 5


class GateReplayReport:
    """Joins gate reviews to trend entries and applies the Part A decision rule."""

    def __init__(
        self, entries: list[TrendEntrySchema], reviews: list[TrendGateReviewSchema]
    ) -> None:
        by_key = {(r.symbol, r.as_of): r for r in reviews}
        missing = [e for e in entries if (e.symbol, e.as_of) not in by_key]
        if missing:
            msg = f"{len(missing)} entries have no review, first {missing[0].symbol}"
            raise ValueError(msg)
        self._rows = [(e, by_key[(e.symbol, e.as_of)]) for e in entries]

    @property
    def vetoes(self) -> int:
        return sum(r.decision == "VETO" for _, r in self._rows)

    @property
    def veto_value(self) -> float:
        """Minus the summed net P&L of vetoed entries; positive means losers removed."""
        return -sum(e.net_pnl for e, r in self._rows if r.decision == "VETO")

    def decision(self) -> str:
        if self.vetoes > MAX_VETOES:
            return f"KILL: {self.vetoes} vetoes, more than {MAX_VETOES}"
        if self.veto_value < 0:
            return "KILL: vetoed entries made money"
        if self.vetoes == 0:
            return "CONTINUE shadow: no vetoes, the replay is uninformative"
        return "CONTINUE shadow: vetoes removed losing trades (anecdotal, n=15)"

    def render(self) -> str:
        lines = [
            "# Trend news gate replay",
            "",
            "Rules: `evals/preregistrations/2026_11_17_trend_news_gate.md`, Part A.",
            "",
            (
                "| Signal day | Symbol | Weight | Exit | Net P&L % "
                "| Headlines (coin/other) | Votes | Decision | Catalyst |"
            ),
            "|---|---|---|---|---|---|---|---|---|",
        ]
        for entry, review in self._rows:
            votes = "".join(s.verdict[0] for s in review.samples) or "-"
            catalysts = sorted(
                {s.catalyst for s in review.samples if s.verdict == "VETO"}
            )
            lines.append(
                f"| {entry.signal_day} | {entry.symbol} | {entry.weight:.3f}"
                f" | {entry.exit_day or 'open'} | {entry.net_pnl * 100:+.2f}"
                f" | {review.coin_headlines}/{review.other_headlines} | {votes}"
                f" | {review.decision} | {'; '.join(catalysts)} |"
            )
        prompts = sorted({r.prompt_sha for _, r in self._rows})
        lines += [
            "",
            f"- Entries: {len(self._rows)}, vetoes: {self.vetoes}",
            f"- Veto value: {self.veto_value * 100:+.2f}% of equity",
            f"- Prompt hash: {', '.join(prompts)}",
            f"- Decision: {self.decision()}",
            "",
        ]
        return "\n".join(lines)
