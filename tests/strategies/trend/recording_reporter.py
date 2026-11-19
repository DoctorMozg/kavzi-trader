from kavzi_trader.strategies.trend.trend_halving_schema import TrendHalvingSchema
from kavzi_trader.strategies.trend.trend_view_schema import TrendViewSchema


class RecordingReporter:
    def __init__(self, error: Exception | None = None) -> None:
        self.views: list[TrendViewSchema] = []
        self.halvings: list[TrendHalvingSchema] = []
        self._error = error

    async def record_trend_view(self, view: TrendViewSchema) -> None:
        self.views.append(view)
        if self._error is not None:
            raise self._error

    async def record_halving(self, halving: TrendHalvingSchema) -> None:
        self.halvings.append(halving)
