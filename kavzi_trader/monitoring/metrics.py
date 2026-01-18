from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class MetricsSnapshotSchema(BaseModel):
    """Snapshot of in-memory metrics."""

    counters: Annotated[dict[str, int], Field(default_factory=dict)]
    gauges: Annotated[dict[str, float], Field(default_factory=dict)]
    histograms: Annotated[dict[str, list[float]], Field(default_factory=dict)]

    model_config = ConfigDict(frozen=True)


class MetricsRegistry:
    """In-memory registry for counters, gauges, and histograms."""

    def __init__(self) -> None:
        self._counters: dict[str, int] = {}
        self._gauges: dict[str, float] = {}
        self._histograms: dict[str, list[float]] = {}

    def inc_counter(self, name: str, value: int = 1) -> None:
        self._counters[name] = self._counters.get(name, 0) + value

    def set_gauge(self, name: str, value: float) -> None:
        self._gauges[name] = value

    def observe(self, name: str, value: float) -> None:
        self._histograms.setdefault(name, []).append(value)

    def snapshot(self) -> MetricsSnapshotSchema:
        return MetricsSnapshotSchema(
            counters=dict(self._counters),
            gauges=dict(self._gauges),
            histograms={k: list(v) for k, v in self._histograms.items()},
        )
