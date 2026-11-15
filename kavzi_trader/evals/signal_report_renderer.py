from kavzi_trader.evals.markdown_format import NA, Md
from kavzi_trader.evals.signal_edge_schema import (
    BracketEdgeSchema,
    EdgeStatSchema,
    SignalEdgeSchema,
)
from kavzi_trader.evals.signal_sampler import SIDES


class SignalReportRenderer:
    """Markdown report of signal edge across one or more brackets."""

    def __init__(self, stride: int, history: int, symbols: list[str]) -> None:
        self._stride = stride
        self._history = history
        self._symbols = symbols

    def render(self, results: list[BracketEdgeSchema]) -> str:
        intro = (
            f"Every {self._stride}th 15m bar of {', '.join(self._symbols)}; "
            f"live indicators over the trailing {self._history} bars and the live "
            "ConfluenceCalculator. R is the result of taking that side with the "
            "bracket (same-bar SL+TP counts as SL, timeout marked to market), "
            "before fees. Lift is fired minus not-fired mean R, so market drift "
            "cancels out. ± is a 95% interval widened for overlapping outcome "
            "windows; the fee is the taker round trip in R."
        )
        blocks = ["# Signal edge report", intro, self._verdicts(results)]
        blocks += [self._bracket(result) for result in results]
        return "\n\n".join(blocks) + "\n"

    def summary(self, results: list[BracketEdgeSchema]) -> list[str]:
        lines = []
        for result in results:
            found = self._edges(result)
            text = ", ".join(found) if found else "no signal with lift"
            lines.append(
                f"{result.bracket.label}: {result.samples} bars, "
                f"fee {result.mean_fee_r:.3f}R, {text}"
            )
        return lines

    def _verdicts(self, results: list[BracketEdgeSchema]) -> str:
        rows = [
            [
                result.bracket.label,
                f"{result.mean_fee_r:.3f}",
                ", ".join(self._edges(result)) or "none",
            ]
            for result in results
        ]
        return Md.section(
            "Signals whose lift excludes zero",
            Md.table(["bracket", "fee (R)", "signals (side, lift)"], rows),
        )

    @staticmethod
    def _edges(result: BracketEdgeSchema) -> list[str]:
        found = []
        for edge in result.signals:
            lift, ci = edge.lift, edge.lift_ci95
            if lift is not None and ci is not None and abs(lift) > ci:
                found.append(f"{edge.side} {edge.signal} {lift:+.3f}")
        return found

    def _bracket(self, result: BracketEdgeSchema) -> str:
        shares = ", ".join(f"{k} {v:.1%}" for k, v in result.label_shares.items())
        base = ", ".join(f"{s} {self._fmt(result.base[s])}" for s in SIDES)
        head = (
            f"{result.samples} bars. Labels: {shares}. "
            f"All bars: {base}. Round-trip fee {result.mean_fee_r:.3f}R. "
            f"Interval widening x{result.ci_widening:.2f}."
        )
        signal_rows = [
            self._signal_row(edge)
            for side in SIDES
            for edge in result.signals
            if edge.side == side
        ]
        signals = Md.table(
            ["side", "signal", "fires", "fired: mean R", "win", "not fired", "lift"],
            signal_rows,
        )
        buckets = Md.table(
            ["side", "score", "bars", "mean R", "win"],
            [
                [
                    b.side,
                    b.bucket,
                    str(b.stat.n),
                    self._fmt(b.stat),
                    Md.rate(b.stat.win_rate),
                ]
                for b in result.score_buckets
            ],
        )
        return Md.section(result.bracket.label, head, signals, buckets)

    def _signal_row(self, edge: SignalEdgeSchema) -> list[str]:
        return [
            edge.side,
            edge.signal,
            f"{edge.fired_share:.1%}",
            self._fmt(edge.fired),
            Md.rate(edge.fired.win_rate),
            self._fmt(edge.not_fired),
            self._lift(edge),
        ]

    @staticmethod
    def _lift(edge: SignalEdgeSchema) -> str:
        if edge.lift is None:
            return NA
        ci = NA if edge.lift_ci95 is None else f"{edge.lift_ci95:.3f}"
        return f"{edge.lift:+.3f} ±{ci}"

    @staticmethod
    def _fmt(stat: EdgeStatSchema) -> str:
        if stat.mean_r is None:
            return NA
        ci = NA if stat.ci95 is None else f"{stat.ci95:.3f}"
        return f"{stat.mean_r:+.3f} ±{ci}"
