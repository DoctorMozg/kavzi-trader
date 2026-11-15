from collections import Counter

from kavzi_trader.evals.baseline_returns import RANDOM_SEED, BaselineReturns
from kavzi_trader.evals.confusion_metrics import CLASSES
from kavzi_trader.evals.joined_case_schema import TRADE_SIDES, JoinedCaseSchema
from kavzi_trader.evals.markdown_format import Md
from kavzi_trader.evals.outcome_renderer import R_HEADERS, stats_row
from kavzi_trader.evals.r_stats_schema import RStatsSchema
from kavzi_trader.evals.sim_trade_schema import SimTradeSchema
from kavzi_trader.evals.stage_stats import StageStats


class ForcedTraderRenderer:
    """Markdown for the Trader on cases the Analyst gate would have stopped."""

    def __init__(
        self, scored: list[JoinedCaseSchema], forced_trades: list[SimTradeSchema]
    ) -> None:
        self._forced = [j for j in scored if j.result.trader_forced]
        self._trades = forced_trades

    @property
    def has_cases(self) -> bool:
        return bool(self._forced)

    def section(self) -> str:
        return Md.section(
            "Trader on forced cases",
            f"{len(self._forced)} cases stopped at the Analyst gate and ran the "
            "Trader anyway (--force-trader), with the Analyst's own decision as "
            "context. They are not bot trades in the live decision matrix above.",
            "Trader action per label:\n\n" + self._actions(),
            "Direction agreement with the label:\n\n" + self._agreement(),
            "Simulated R of the Trader's own entry/SL/TP against baselines on the "
            f"same {len(self._forced)} cases (random seed {RANDOM_SEED}):\n\n"
            + self._returns(),
        )

    def _actions(self) -> str:
        actions = StageStats(self._forced).forced_trader_actions()
        columns = sorted({a for c in actions.values() for a in c})
        rows = [
            [
                label,
                str(sum(actions.get(label, Counter()).values())),
                *(str(actions.get(label, Counter())[a]) for a in columns),
            ]
            for label in CLASSES
        ]
        return Md.table(["label", "n", *columns], rows)

    def _agreement(self) -> str:
        rows = []
        for label in CLASSES:
            members = [j for j in self._forced if j.case.label.value == label]
            sides = [s for j in members if (s := j.forced_trader_side) is not None]
            agree = (
                Md.pct(sides.count(label), len(sides)) if label in TRADE_SIDES else "-"
            )
            rows.append([label, str(len(members)), str(len(sides)), agree])
        return Md.table(["label", "cases", "trades placed", "side = label"], rows)

    def _returns(self) -> str:
        baselines = BaselineReturns([j.case for j in self._forced])
        own = RStatsSchema.from_r([t.r_multiple for t in self._trades])
        rows = [
            stats_row("Trader (forced cases)", own),
            stats_row("oracle", baselines.oracle()),
            stats_row("always long", baselines.always_long()),
            stats_row("always short", baselines.always_short()),
            stats_row("random side", baselines.random_side()),
            stats_row("random side, expected", baselines.random_side_expected()),
        ]
        return Md.table(R_HEADERS, rows)
