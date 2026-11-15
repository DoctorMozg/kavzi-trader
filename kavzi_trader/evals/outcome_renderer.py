from collections import defaultdict
from collections.abc import Callable

from kavzi_trader.evals.baseline_returns import RANDOM_SEED, BaselineReturns
from kavzi_trader.evals.joined_case_schema import JoinedCaseSchema
from kavzi_trader.evals.markdown_format import Md
from kavzi_trader.evals.r_stats_schema import RStatsSchema
from kavzi_trader.evals.sim_trade_schema import SimTradeSchema
from kavzi_trader.evals.stage_ops import StageOps


def _stats_row(name: str, stats: RStatsSchema, *, win: bool = True) -> list[str]:
    return [
        name,
        str(stats.trades),
        Md.rate(stats.win_rate) if win else "-",
        Md.num(stats.mean_r),
        Md.num(stats.total_r),
    ]


_R_HEADERS = ["strategy", "trades", "win rate", "mean R", "total R"]


class OutcomeRenderer:
    """Markdown for the simulated outcome, ops and breakdown sections."""

    def __init__(
        self,
        scored: list[JoinedCaseSchema],
        trades: list[SimTradeSchema],
        stages: dict[str, StageOps],
        results_count: int,
    ) -> None:
        self._scored = scored
        self._trades = trades
        self._stages = stages
        self._results_count = results_count

    def simulation(self) -> str:
        baselines = BaselineReturns([j.case for j in self._scored])
        rows = [
            _stats_row("bot (Trader's own entry/SL/TP)", self._r_stats(self._trades)),
            _stats_row("oracle (label side, dataset bracket)", baselines.oracle()),
            _stats_row("always long", baselines.always_long()),
            _stats_row("always short", baselines.always_short()),
            _stats_row(f"random side (seed {RANDOM_SEED})", baselines.random_side()),
            _stats_row(
                "random side, expected", baselines.random_side_expected(), win=False
            ),
        ]
        return Md.section(
            "Simulated outcome",
            "Each bot trade is walked over cached 15m candles from the decision close "
            "for up to the dataset horizon; same-bar SL+TP counts as SL and a timeout "
            "is marked to market. R = PnL / SL distance. Fees are ignored. Baselines "
            "use the dataset bracket (1.5 ATR stop, 3 ATR target) over all scored "
            "cases.",
            Md.table(_R_HEADERS, rows),
            "R of the bot's trades by label:\n\n" + self._grouped(lambda t: t.label),
            "R of the bot's trades by regime:\n\n" + self._grouped(lambda t: t.regime),
        )

    def ops(self) -> str:
        names = list(self._stages)
        lat = Md.table(
            ["stage", "cases", "requests", "retries", "p50 ms", "p95 ms", "max ms"],
            [
                [
                    n,
                    str(s.cases),
                    str(s.requests),
                    str(s.retries),
                    Md.num(s.latency_ms(50), 0),
                    Md.num(s.latency_ms(95), 0),
                    Md.num(s.max_latency_ms, 0),
                ]
                for n, s in self._stages.items()
            ],
        )
        total_cost = sum(s.cost_usd for s in self._stages.values())
        cost = Md.table(
            ["stage", "cost USD", "per case", "unpriced cases"],
            [
                [
                    n,
                    f"{s.cost_usd:.4f}",
                    f"{s.cost_usd / max(s.cases, 1):.4f}",
                    str(s.unpriced),
                ]
                for n, s in self._stages.items()
            ],
        )
        tokens = Md.table(
            ["stage", "input", "output", "cache read", "cache write"],
            [
                [
                    n,
                    str(s.input_tokens),
                    str(s.output_tokens),
                    str(s.cache_read_tokens),
                    str(s.cache_write_tokens),
                ]
                for n, s in self._stages.items()
            ],
        )
        failures = Md.table(
            ["stage", "refusals", "parse failures (no_decision)", "API errors"],
            [
                [n, str(s.refusals), str(s.parse_failures), str(s.api_errors)]
                for n in names
                for s in [self._stages[n]]
            ],
        )
        per_case = total_cost / self._results_count if self._results_count else None
        return Md.section(
            "Ops",
            lat,
            cost,
            f"Total ${total_cost:.4f}, per case ${Md.num(per_case, 4)} "
            f"over {self._results_count} results. Retries = requests minus cases that "
            "reached the stage.",
            "Tokens (input includes cache tokens):\n\n" + tokens,
            failures,
        )

    def breakdowns(self) -> str:
        return Md.section(
            "Breakdowns",
            "By regime:\n\n" + self._breakdown(lambda j: j.case.regime),
            "By tier:\n\n" + self._breakdown(lambda j: j.case.tier),
        )

    def _breakdown(self, key: Callable[[JoinedCaseSchema], str]) -> str:
        groups: dict[str, list[JoinedCaseSchema]] = defaultdict(list)
        for joined in self._scored:
            groups[key(joined)].append(joined)
        by_case = {t.case_id: t for t in self._trades}
        rows = []
        for name, members in sorted(groups.items()):
            correct = sum(j.final_action == j.case.label.value for j in members)
            r = [
                by_case[j.case.case_id].r_multiple
                for j in members
                if j.case.case_id in by_case
            ]
            stats = RStatsSchema.from_r(r)
            rows.append(
                [
                    name,
                    Md.pct(correct, len(members)),
                    str(stats.trades),
                    Md.num(stats.mean_r),
                    Md.num(stats.total_r),
                ]
            )
        return Md.table(["group", "accuracy", "trades", "mean R", "total R"], rows)

    def _grouped(self, key: Callable[[SimTradeSchema], str]) -> str:
        groups: dict[str, list[SimTradeSchema]] = defaultdict(list)
        for trade in self._trades:
            groups[key(trade)].append(trade)
        rows = [_stats_row(n, self._r_stats(t)) for n, t in sorted(groups.items())]
        return Md.table(["group", *_R_HEADERS[1:]], rows) if rows else "No trades."

    @staticmethod
    def _r_stats(trades: list[SimTradeSchema]) -> RStatsSchema:
        return RStatsSchema.from_r([t.r_multiple for t in trades])
