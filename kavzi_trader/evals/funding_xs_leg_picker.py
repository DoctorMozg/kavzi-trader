from kavzi_trader.evals.funding_xs_legs_schema import FundingXsLegsSchema


class FundingXsLegPicker:
    """Ranks symbols by funding score and takes both ends of the ranking."""

    def __init__(self, legs: int) -> None:
        self._legs = legs

    def pick(self, scores: dict[str, float]) -> FundingXsLegsSchema:
        if len(scores) < 2 * self._legs:
            msg = f"need {2 * self._legs} scored symbols, got {len(scores)}"
            raise ValueError(msg)
        # Symbol name breaks ties so a rerun picks the same legs.
        ranked = sorted(scores, key=lambda s: (scores[s], s))
        return FundingXsLegsSchema(
            longs=ranked[: self._legs], shorts=ranked[-self._legs :]
        )
