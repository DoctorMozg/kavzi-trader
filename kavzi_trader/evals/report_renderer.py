from collections import Counter

from kavzi_trader.evals.confusion_metrics import CLASSES, ConfusionMetrics
from kavzi_trader.evals.joined_case_schema import TRADE_SIDES
from kavzi_trader.evals.loaded_run_schema import LoadedRunSchema
from kavzi_trader.evals.markdown_format import Md
from kavzi_trader.evals.stage_ops import StageOps
from kavzi_trader.evals.stage_stats import (
    CONFLUENCE_BUCKETS,
    StageStats,
    confluence_bucket,
)

_STOP_ORDER = (
    "scout",
    "analyst_skipped",
    "analyst_error",
    "analyst_gate",
    "trader_gate",
    "trader_error",
    "trader",
)


class ReportRenderer:
    """Markdown for the header, funnel, final-decision and per-stage sections."""

    def __init__(
        self, run: LoadedRunSchema, analyst: StageOps, trader: StageOps
    ) -> None:
        self._run = run
        self._analyst = analyst
        self._trader = trader
        self._stats = StageStats(run.scored)

    def header(self) -> str:
        h = self._run.header
        config = Md.table(
            ["Setting", "Value"],
            [
                ["Analyst", f"{h.analyst_model} (effort {h.analyst_effort})"],
                ["Trader", f"{h.trader_model} (effort {h.trader_effort})"],
                ["Provider", h.provider],
                ["Bypass scout", str(h.bypass_scout)],
                ["Force trader", str(h.force_trader)],
                ["Dataset", h.dataset],
                ["Git hash", h.git_hash or "n/a"],
                ["Concurrency", str(h.concurrency)],
            ],
        )
        statuses = Counter(r.status for r in self._run.results)
        counts = ", ".join(f"{k}={v}" for k, v in sorted(statuses.items()))
        cost = self._analyst.cost_usd + self._trader.cost_usd
        busy_s = (self._analyst.total_latency_ms + self._trader.total_latency_ms) / 1000
        wall_min = busy_s / h.concurrency / 60
        errored = [f"- `{r.case_id}`: {r.error}" for r in self._run.errored]
        return Md.section(
            "Run",
            config,
            f"Cases by status: {counts}",
            "Errored cases:\n" + "\n".join(errored) if errored else "No errored cases.",
            f"Total cost: ${cost:.4f}. Wall time is not recorded; estimated at "
            f"{wall_min:.1f} min (summed stage latency / concurrency).",
        )

    def funnel(self) -> str:
        labels = list(CLASSES)
        by_stop: dict[str, Counter[str]] = {s: Counter() for s in _STOP_ORDER}
        for r in self._run.results:
            by_stop[r.stopped_at or r.status][r.label] += 1
        rows = []
        for stop in _STOP_ORDER:
            counts = [by_stop[stop][label] for label in labels]
            rows.append([stop, *map(str, counts), str(sum(counts))])
        total = [sum(by_stop[s][label] for s in _STOP_ORDER) for label in labels]
        rows.append(["total", *map(str, total), str(sum(total))])
        return Md.section(
            "Pipeline funnel", Md.table(["stopped_at", *labels, "all"], rows)
        )

    def decisions(self, bot: ConfusionMetrics, live: ConfusionMetrics | None) -> str:
        blocks = [self._confusion("Bot as run", bot)]
        if live is not None:
            blocks.append(
                self._confusion(
                    "As if the live Scout had applied (bypassed SKIP = NO_TRADE)", live
                )
            )
        return Md.section("Final decision vs label", *blocks)

    def _confusion(self, title: str, metrics: ConfusionMetrics) -> str:
        matrix = Md.table(
            ["label \\ bot", *CLASSES],
            [[a, *(str(metrics.count(a, p)) for p in CLASSES)] for a in CLASSES],
        )
        per_class = Md.table(
            ["class", "support", "predicted", "precision", "recall", "F1"],
            [
                [
                    name,
                    str(m.support),
                    str(m.predicted),
                    Md.rate(m.precision),
                    Md.rate(m.recall),
                    Md.rate(m.f1),
                ]
                for name, m in metrics.per_class().items()
            ],
        )
        totals = (
            f"Accuracy {Md.rate(metrics.accuracy)} over {metrics.total} cases, "
            f"macro-F1 {Md.rate(metrics.macro_f1)}. Trade precision "
            f"{Md.pct(metrics.trade_hits, metrics.trades)}: of the cases the bot "
            "traded, "
            "the share where it picked the label's side."
        )
        return f"### {title}\n\n{matrix}\n\n{per_class}\n\n{totals}"

    def stages(self) -> str:
        return Md.section(
            "Per stage",
            self._scout(),
            self._analyst_section(),
            self._trader_section(),
        )

    def _scout(self) -> str:
        verdicts = self._stats.scout_verdicts()
        rows = []
        for label in CLASSES:
            got = verdicts.get(label, Counter())
            rows.append(
                [label, Md.pct(got["INTERESTING"], sum(got.values())), str(got["SKIP"])]
            )
        tradeable = [verdicts.get(s, Counter()) for s in TRADE_SIDES]
        hits = sum(c["INTERESTING"] for c in tradeable)
        total = sum(sum(c.values()) for c in tradeable)
        return (
            "### Scout (verdict is real even when bypassed)\n\n"
            + Md.table(["label", "INTERESTING rate", "SKIP"], rows)
            + f"\n\nRecall on tradeable labels: {Md.pct(hits, total)}"
        )

    def _analyst_section(self) -> str:
        validity = self._stats.analyst_validity()
        directions = self._stats.valid_directions()
        scores = self._stats.confluence_scores()
        rows = []
        for label in CLASSES:
            got = validity.get(label, Counter())
            valid_dirs = directions.get(label, Counter())
            agree = (
                Md.pct(valid_dirs[label], sum(valid_dirs.values()))
                if label in TRADE_SIDES
                else "-"
            )
            rows.append(
                [
                    label,
                    Md.pct(got["valid"], sum(got.values())),
                    str(got["no_verdict"]),
                    agree,
                ]
            )
        conf_rows = []
        for label in CLASSES:
            values = scores.get(label, [])
            buckets = Counter(confluence_bucket(v) for v in values)
            mean = Md.num(sum(values) / len(values)) if values else "n/a"
            conf_rows.append(
                [
                    label,
                    str(len(values)),
                    mean,
                    *(str(buckets[b]) for b in CONFLUENCE_BUCKETS),
                ]
            )
        cells = self._stats.validity_vs_trade_label()
        grid = Md.table(
            ["", "label is trade", "label NO_TRADE"],
            [
                [
                    "setup_valid",
                    str(cells["valid/trade"]),
                    str(cells["valid/no_trade"]),
                ],
                [
                    "setup invalid",
                    str(cells["invalid/trade"]),
                    str(cells["invalid/no_trade"]),
                ],
            ],
        )
        return (
            "### Analyst\n\n"
            + Md.table(
                ["label", "setup_valid rate", "no verdict", "direction agrees (valid)"],
                rows,
            )
            + "\n\nConfluence score per label:\n\n"
            + Md.table(["label", "n", "mean", *CONFLUENCE_BUCKETS], conf_rows)
            + "\n\nsetup_valid vs label is a trade:\n\n"
            + grid
            + f"\n\nAnalyst ran on {self._analyst.cases} cases."
        )

    def _trader_section(self) -> str:
        actions = self._stats.trader_actions()
        columns = sorted({a for c in actions.values() for a in c})
        live = sum(sum(c.values()) for c in actions.values())
        rows = [
            [
                label,
                str(sum(actions.get(label, Counter()).values())),
                *(str(actions.get(label, Counter())[a]) for a in columns),
            ]
            for label in CLASSES
        ]
        return f"### Trader (cases that reached it live: {live})\n\n" + Md.table(
            ["label", "n", *columns], rows
        )
