from kavzi_trader.evals.markdown_format import Md
from kavzi_trader.evals.trend_report_renderer import TrendReportRenderer
from kavzi_trader.evals.trend_result_schema import TrendResultSchema
from kavzi_trader.evals.walk_forward_choice_schema import WalkForwardChoiceSchema
from kavzi_trader.evals.walk_forward_result_schema import WalkForwardResultSchema


class WalkForwardReportRenderer:
    """Markdown report: yearly lookback choices, then the stitched result."""

    def __init__(self, preregistration: str) -> None:
        self._preregistration = preregistration
        self._trend = TrendReportRenderer(
            "Walk-forward Donchian long/flat",
            preregistration,
            "This walk-forward result decides on its own.",
        )

    def render(
        self, result: WalkForwardResultSchema, hindsight: TrendResultSchema
    ) -> str:
        oos = result.out_of_sample
        candidates = sorted(result.choices[0].scores)
        intro = (
            "Each test year trades the lookback with the best net Sharpe from "
            f"{result.train_first_day} to the day before that year. Candidates: "
            f"{', '.join(map(str, candidates))}. Symbols: {', '.join(oos.symbols)}; "
            f"{oos.first_day} to {oos.last_day} ({oos.days} days). Rules: "
            f"evals/preregistrations/{self._preregistration}."
        )
        blocks = [
            "# Walk-forward trend backtest",
            intro,
            self._choices(result.choices, candidates),
            *self._trend.sections(oos),
            self._hindsight(oos, hindsight),
        ]
        return "\n\n".join(blocks) + "\n"

    def criterion_met(self, result: WalkForwardResultSchema) -> bool:
        return self._trend.criterion_met(result.out_of_sample)

    @staticmethod
    def _choices(choices: list[WalkForwardChoiceSchema], candidates: list[int]) -> str:
        rows = [
            [
                f"{c.window.first_day} to {c.window.last_day}",
                str(c.lookback),
                *(Md.num(c.scores[lb]) for lb in candidates),
            ]
            for c in choices
        ]
        headers = ["Test period", "Chosen", *(f"L{lb}" for lb in candidates)]
        return Md.section(
            "Lookback chosen each year (training net Sharpe per candidate)",
            Md.table(headers, rows),
        )

    @staticmethod
    def _hindsight(oos: TrendResultSchema, hindsight: TrendResultSchema) -> str:
        text = (
            "Exploratory, not part of the decision: the lookback the paper rule uses, "
            "picked after seeing 2022-2026, scored "
            f"net Sharpe {Md.num(hindsight.net.sharpe)} over the same days, against "
            f"{Md.num(oos.net.sharpe)} walk-forward. The gap is what hindsight added."
        )
        return Md.section("Hindsight comparison", text)
