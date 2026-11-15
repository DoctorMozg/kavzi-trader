import logging
from pathlib import Path

from kavzi_trader.evals.candle_cache import CandleCache
from kavzi_trader.evals.confusion_metrics import ConfusionMetrics
from kavzi_trader.evals.forced_trader_renderer import ForcedTraderRenderer
from kavzi_trader.evals.loaded_run_schema import LoadedRunSchema
from kavzi_trader.evals.markdown_format import Md
from kavzi_trader.evals.outcome_renderer import OutcomeRenderer
from kavzi_trader.evals.report_renderer import ReportRenderer
from kavzi_trader.evals.stage_ops import StageOps
from kavzi_trader.evals.trade_simulator import TradeSimulator

logger = logging.getLogger(__name__)


class RunReportBuilder:
    """Scores one loaded run and renders the Markdown report plus a short summary."""

    def __init__(self, run: LoadedRunSchema, cache_dir: Path) -> None:
        self._run = run
        cases = run.scored
        self._bot = ConfusionMetrics(
            [j.case.label.value for j in cases], [j.final_action for j in cases]
        )
        self._live = (
            ConfusionMetrics(
                [j.case.label.value for j in cases], [j.live_action for j in cases]
            )
            if run.header.bypass_scout
            else None
        )
        simulator = TradeSimulator(CandleCache(cache_dir, "15m"))
        self._trades = [t for j in cases if (t := simulator.simulate(j)) is not None]
        self._forced_trades = [
            t
            for j in cases
            if j.result.trader_forced
            and (t := simulator.simulate(j, forced=True)) is not None
        ]
        records = run.results
        self._stages = {
            "analyst": StageOps([r.analyst.metrics for r in records if r.analyst]),
            "trader": StageOps([r.trader.metrics for r in records if r.trader]),
        }

    def markdown(self) -> str:
        report = ReportRenderer(
            self._run, self._stages["analyst"], self._stages["trader"]
        )
        outcomes = OutcomeRenderer(
            self._run.scored, self._trades, self._stages, len(self._run.results)
        )
        forced = ForcedTraderRenderer(self._run.scored, self._forced_trades)
        title = f"# Eval report: {self._run.header.run_id}"
        sections = [
            title,
            report.header(),
            report.funnel(),
            report.decisions(self._bot, self._live),
            report.stages(),
            outcomes.simulation(),
            *([forced.section()] if forced.has_cases else []),
            outcomes.ops(),
            outcomes.breakdowns(),
        ]
        return "\n\n".join(sections) + "\n"

    def summary(self) -> list[str]:
        r_values = [t.r_multiple for t in self._trades]
        mean_r = sum(r_values) / len(r_values) if r_values else None
        cost = sum(s.cost_usd for s in self._stages.values())
        lines = [
            f"Cases: {len(self._run.scored)} scored, {len(self._run.errored)} errored",
            (
                f"Accuracy {Md.rate(self._bot.accuracy)}, "
                f"macro-F1 {Md.rate(self._bot.macro_f1)}, trade precision "
                f"{Md.pct(self._bot.trade_hits, self._bot.trades)}"
            ),
            (
                f"Simulated: {len(r_values)} trades, mean R {Md.num(mean_r)}, "
                f"total R {Md.num(sum(r_values))}"
            ),
            f"Cost ${cost:.4f}",
        ]
        if self._live is not None:
            lines.insert(2, f"Live-Scout view: accuracy {Md.rate(self._live.accuracy)}")
        return lines
