from kavzi_trader.evals.markdown_format import Md
from kavzi_trader.evals.timing_arm_outcome_schema import TimingArmOutcomeSchema
from kavzi_trader.evals.timing_run_schema import TimingRunSchema
from kavzi_trader.evals.timing_verdict import TimingVerdict
from kavzi_trader.evals.trend_result_schema import TrendResultSchema


def _pct(value: float) -> str:
    return f"{100 * value:.1f}%"


def _interval(lower: float, upper: float) -> str:
    return f"[{lower:+.3f}, {upper:+.3f}]"


class TimingReportRenderer:
    """Markdown report of the timing arms on one universe."""

    def __init__(self, verdict: TimingVerdict, preregistration: str | None) -> None:
        self._verdict = verdict
        self._prereg = preregistration

    def render(self, run: TimingRunSchema) -> str:
        base = run.base.result
        rules = (
            f"Rules: evals/preregistrations/{self._prereg}."
            if self._prereg
            else "Exploratory: no preregistration decides on this run."
        )
        intro = (
            f"Universe: {run.universe}, {len(base.symbols)} symbols; {base.first_day} "
            f"to {base.last_day} ({base.days} days). Base: mid-exit Donchian long/flat "
            f"lookback 20 on daily bars. Vol-spike halving is excluded from every "
            f"arm. {rules}"
        )
        blocks = [
            "# Trend timing",
            intro,
            Md.section("Checks", self._checks(run)),
            Md.section("Summary", self._summary(run)),
            Md.section("Paired comparison", self._paired(run)),
            Md.section("Sharpe by year", self._by_year(run)),
        ]
        return "\n\n".join(blocks) + "\n"

    def _checks(self, run: TimingRunSchema) -> str:
        quality = [
            [
                f"{q.hours}h",
                str(q.gap_bars),
                f"{q.day_end_mismatches}/{q.listed_days}",
                f"{q.max_day_end_gap:.2e}",
            ]
            for q in run.quality
        ]
        table = Md.table(
            ["Bars", "Gap bars carried", "Day closes off the daily bar", "Max gap"],
            quality,
        )
        sharpe = run.base.result.net.sharpe
        if run.reproduction_error is None:
            repro = f"Reproduction: base Sharpe {sharpe:.3f}, as in 2026-11-19: ok."
        else:
            repro = f"Reproduction: VOID, {run.reproduction_error}."
        integrity = (
            "Bars: day closes agree with the daily bars: ok."
            if run.quality_error is None
            else f"Bars: VOID, {run.quality_error}."
        )
        return f"{repro}\n\n{integrity}\n\n{table}"

    def _summary(self, run: TimingRunSchema) -> str:
        base = run.base
        rows = [self._row("base", base.result, base.trades_per_year)]
        rows += [
            self._row(o.arm.label, o.scored.result, o.scored.trades_per_year)
            for o in run.arms
        ]
        headers = [
            "Arm",
            "Net Sharpe",
            "Sharpe over cash",
            "Return",
            "Max drawdown",
            "Trades per year",
            "Turnover (x NAV)",
            "Cost drag",
        ]
        return Md.table(headers, rows)

    @staticmethod
    def _row(label: str, result: TrendResultSchema, trades: float) -> list[str]:
        net = result.net
        return [
            label,
            Md.num(net.sharpe, 3),
            Md.num(net.sharpe_over_cash, 3),
            _pct(net.annual_return),
            _pct(net.max_drawdown),
            f"{trades:.0f}",
            Md.num(result.turnover_per_year),
            _pct(result.cost_drag),
        ]

    def _paired(self, run: TimingRunSchema) -> str:
        first = run.arms[0].adjusted
        text = (
            f"Sharpe difference (arm - base) over the same days. Intervals: 90%, and "
            f"the Bonferroni-adjusted {100 * first.confidence:.2f}% per arm "
            f"({first.resamples} stationary-bootstrap resamples, mean block "
            f"{first.mean_block_days} days)."
        )
        headers = [
            "Arm",
            "Difference",
            "90% interval",
            "Adjusted interval",
            "Criterion",
        ]
        rows = [
            [
                o.arm.label,
                f"{o.paired.difference:+.3f}",
                _interval(o.paired.lower, o.paired.upper),
                _interval(o.adjusted.lower, o.adjusted.upper),
                self._criterion(run.universe, o),
            ]
            for o in run.arms
        ]
        if run.universe == "holdout":
            note = (
                "Criterion on the holdout: CONFIRM if the 90% lower bound > 0, "
                "INCONCLUSIVE if the difference is positive but the interval "
                "reaches zero, FAIL otherwise."
            )
        else:
            rule = (
                "fresh: adjusted lower bound > 0."
                if run.universe == "fresh"
                else "trading: Sharpe difference >= 0."
            )
            note = (
                f"Criterion on this universe, {rule} An arm is an ADOPT candidate "
                "only if it passes on both universes."
            )
        return "\n\n".join([text, Md.table(headers, rows), note])

    def _criterion(self, universe: str, outcome: TimingArmOutcomeSchema) -> str:
        if universe == "holdout":
            return self._verdict.holdout_outcome(outcome.paired)
        if universe == "fresh":
            passed = self._verdict.fresh_passes(outcome.adjusted)
        else:
            passed = self._verdict.trading_passes(outcome.paired)
        return "pass" if passed else "fail"

    @staticmethod
    def _by_year(run: TimingRunSchema) -> str:
        results = [("base", run.base.result)]
        results += [(o.arm.label, o.scored.result) for o in run.arms]
        years = sorted(run.base.result.net.sharpe_by_year)
        rows = [
            [str(y), *(Md.num(r.net.sharpe_by_year.get(y), 3) for _, r in results)]
            for y in years
        ]
        return Md.table(["Year", *(label for label, _ in results)], rows)
