from kavzi_trader.evals.combined_arms_result_schema import CombinedArmsResultSchema
from kavzi_trader.evals.combined_arms_verdict import (
    MAX_HALVING_COST,
    MIN_MID_GAIN,
    CombinedArmsVerdict,
)
from kavzi_trader.evals.markdown_format import Md
from kavzi_trader.evals.validation.paired_sharpe_schema import PairedSharpeSchema


def _pct(value: float) -> str:
    return f"{100 * value:.1f}%"


def _interval(paired: PairedSharpeSchema) -> str:
    return f"{paired.difference:+.3f}, 90% [{paired.lower:+.3f}, {paired.upper:+.3f}]"


class CombinedArmsReportRenderer:
    """Markdown report of the 2x2 exit and halving arms and the paper-rule decision."""

    def __init__(self, preregistration: str | None) -> None:
        self._prereg = preregistration
        self._verdict = CombinedArmsVerdict()

    def render(self, result: CombinedArmsResultSchema) -> str:
        rules = (
            f"Rules: evals/preregistrations/{self._prereg}."
            if self._prereg
            else "Exploratory: no preregistration decides on this run."
        )
        base = result.base
        intro = (
            f"{len(base.symbols)} symbols; {base.first_day} to {base.last_day} "
            f"({base.days} days). {rules}"
        )
        errors = self._verdict.reproduction_errors(result)
        blocks = ["# Mid exit with vol-spike halving", intro]
        if errors:
            blocks.append(
                Md.section(
                    "VOID: reproduction check failed",
                    "A separately scored arm no longer matches its 2026-11-19 "
                    "report, so code or data changed. No decision is taken.\n\n"
                    + "\n".join(f"- {e}" for e in errors),
                )
            )
        blocks += [self._summary(result), self._paired(result)]
        if not errors:
            blocks.append(self._decisions(result))
        return "\n\n".join(blocks) + "\n"

    @staticmethod
    def _summary(result: CombinedArmsResultSchema) -> str:
        arms = [
            ("Low exit", result.base),
            ("Mid exit", result.mid),
            ("Low exit + halving", result.halving),
            ("Mid exit + halving", result.mid_halving),
        ]
        rows = [
            [
                name,
                Md.num(r.net.sharpe, 3),
                Md.num(r.net.sharpe_over_cash, 3),
                _pct(r.net.annual_return),
                _pct(r.net.annual_vol),
                _pct(r.net.max_drawdown),
            ]
            for name, r in arms
        ]
        years = sorted(result.base.net.sharpe_by_year)
        year_rows = [
            [str(y), *(Md.num(r.net.sharpe_by_year.get(y)) for _, r in arms)]
            for y in years
        ]
        spikes = (
            f"Symbol-days with a spike while held: {result.spike_days_base} under "
            f"the low exit, {result.spike_days_mid} under the mid exit."
        )
        return Md.section(
            "Arms",
            Md.table(
                ["Arm", "Sharpe", "Over cash", "Return", "Vol", "Max drawdown"], rows
            ),
            spikes,
            Md.table(["Year", *(name for name, _ in arms)], year_rows),
        )

    @staticmethod
    def _paired(result: CombinedArmsResultSchema) -> str:
        rows = [
            ["Mid exit gain, halving on (mid+halving - halving)",
             _interval(result.mid_gain_with_halving)],
            ["Mid exit gain, halving off (mid - base)",
             _interval(result.mid_gain_alone)],
            ["Halving change under the mid exit (mid+halving - mid)",
             _interval(result.halving_change_under_mid)],
            ["Halving change under the low exit (halving - base)",
             _interval(result.halving_change_under_base)],
            ["Both changes (mid+halving - base)", _interval(result.combined_vs_base)],
        ]  # fmt: skip
        return Md.section(
            "Paired Sharpe differences",
            Md.table(["Comparison", "Difference"], rows),
        )

    def _decisions(self, result: CombinedArmsResultSchema) -> str:
        gain = result.mid_gain_with_halving.difference
        cost = -result.halving_change_under_mid.difference
        mid = "KEEP" if self._verdict.keep_mid(result) else "DROP"
        halving = "KEEP" if self._verdict.keep_halving(result) else "DROP"
        return Md.section(
            "Decisions",
            f"- Mid exit: {mid} (gain with halving on {gain:+.3f}, needs "
            f">= {MIN_MID_GAIN}).\n"
            f"- Halving: {halving} (Sharpe cost under the mid exit {cost:+.3f}, "
            f"allowed <= {MAX_HALVING_COST}).\n"
            f"- Paper rule: {self._verdict.paper_rule(result)}.",
        )
