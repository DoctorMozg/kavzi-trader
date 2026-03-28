from datetime import UTC, datetime

import pytest

from kavzi_trader.external.cache import ExternalDataCache
from kavzi_trader.external.schemas import (
    ExternalDataSnapshotSchema,
    FearGreedDataSchema,
)
from kavzi_trader.spine.filters.config import FilterConfigSchema
from kavzi_trader.spine.filters.fear_greed_gate import FearGreedGateFilter


@pytest.fixture
def cache() -> ExternalDataCache:
    return ExternalDataCache()


@pytest.fixture
def config() -> FilterConfigSchema:
    return FilterConfigSchema()


@pytest.fixture
def gate(
    cache: ExternalDataCache,
    config: FilterConfigSchema,
) -> FearGreedGateFilter:
    return FearGreedGateFilter(cache, config)


def _set_fgi(cache: ExternalDataCache, value: int) -> None:
    snapshot = ExternalDataSnapshotSchema.model_validate(
        {
            "fear_greed": FearGreedDataSchema.model_validate(
                {
                    "value": value,
                    "classification": "test",
                    "fetched_at": datetime.now(UTC),
                },
            ),
        },
    )
    cache.set_snapshot(snapshot)


def test_extreme_fear_blocks(
    gate: FearGreedGateFilter,
    cache: ExternalDataCache,
) -> None:
    _set_fgi(cache, 5)
    result = gate.evaluate()
    assert not result.is_allowed
    assert "Extreme fear" in (result.reason or "")


def test_extreme_greed_blocks(
    gate: FearGreedGateFilter,
    cache: ExternalDataCache,
) -> None:
    _set_fgi(cache, 95)
    result = gate.evaluate()
    assert not result.is_allowed
    assert "Extreme greed" in (result.reason or "")


def test_boundary_fear_blocks(
    gate: FearGreedGateFilter,
    cache: ExternalDataCache,
) -> None:
    _set_fgi(cache, 10)
    result = gate.evaluate()
    assert not result.is_allowed


def test_boundary_greed_blocks(
    gate: FearGreedGateFilter,
    cache: ExternalDataCache,
) -> None:
    _set_fgi(cache, 90)
    result = gate.evaluate()
    assert not result.is_allowed


def test_just_above_fear_allows(
    gate: FearGreedGateFilter,
    cache: ExternalDataCache,
) -> None:
    _set_fgi(cache, 11)
    result = gate.evaluate()
    assert result.is_allowed


def test_just_below_greed_allows(
    gate: FearGreedGateFilter,
    cache: ExternalDataCache,
) -> None:
    _set_fgi(cache, 89)
    result = gate.evaluate()
    assert result.is_allowed


def test_midrange_allows(
    gate: FearGreedGateFilter,
    cache: ExternalDataCache,
) -> None:
    _set_fgi(cache, 50)
    result = gate.evaluate()
    assert result.is_allowed


def test_no_fgi_data_allows(
    gate: FearGreedGateFilter,
) -> None:
    result = gate.evaluate()
    assert result.is_allowed
    assert "fail-open" in (result.reason or "")


def test_filter_name(gate: FearGreedGateFilter) -> None:
    result = gate.evaluate()
    assert result.name == "fear_greed_gate"
