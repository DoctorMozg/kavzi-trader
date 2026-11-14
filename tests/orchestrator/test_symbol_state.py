import pytest
from pydantic import ValidationError

from kavzi_trader.orchestrator.loops.symbol_state import (
    SymbolStateSchema,
    SymbolStateTracker,
)


@pytest.fixture
def tracker() -> SymbolStateTracker:
    return SymbolStateTracker()


class TestDefaults:
    def test_untouched_symbol_has_zeroed_state(
        self,
        tracker: SymbolStateTracker,
    ) -> None:
        assert tracker.cooldown("BTCUSDT", "LONG") == 0
        assert tracker.consecutive_rejections("BTCUSDT", "LONG") == 0
        assert tracker.consecutive_waits("BTCUSDT", "SHORT") == 0
        assert tracker.consecutive_skips("BTCUSDT") == 0
        assert tracker.skip_eval_interval("BTCUSDT") == 0
        assert tracker.geometry_rejects("BTCUSDT") == 0

    def test_get_returns_the_same_state_object_per_symbol(
        self,
        tracker: SymbolStateTracker,
    ) -> None:
        assert tracker.get("BTCUSDT") is tracker.get("BTCUSDT")
        assert tracker.get("BTCUSDT") is not tracker.get("ETHUSDT")


class TestCooldown:
    def test_cooldown_is_tracked_per_direction(
        self,
        tracker: SymbolStateTracker,
    ) -> None:
        tracker.set_cooldown("BTCUSDT", "LONG", 3)

        assert tracker.cooldown("BTCUSDT", "LONG") == 3
        assert tracker.cooldown("BTCUSDT", "SHORT") == 0

    def test_cooldown_is_tracked_per_symbol(
        self,
        tracker: SymbolStateTracker,
    ) -> None:
        tracker.set_cooldown("BTCUSDT", "LONG", 3)

        assert tracker.cooldown("ETHUSDT", "LONG") == 0

    def test_decrement_counts_down_and_stops_at_zero(
        self,
        tracker: SymbolStateTracker,
    ) -> None:
        tracker.set_cooldown("BTCUSDT", "LONG", 2)

        tracker.decrement_cooldown("BTCUSDT", "LONG")
        assert tracker.cooldown("BTCUSDT", "LONG") == 1
        for _ in range(3):
            tracker.decrement_cooldown("BTCUSDT", "LONG")

        assert tracker.cooldown("BTCUSDT", "LONG") == 0

    def test_decrement_without_cooldown_stays_zero(
        self,
        tracker: SymbolStateTracker,
    ) -> None:
        tracker.decrement_cooldown("BTCUSDT", "SHORT")

        assert tracker.cooldown("BTCUSDT", "SHORT") == 0


class TestRejectionsAndWaits:
    def test_bump_rejection_increments_and_returns_count(
        self,
        tracker: SymbolStateTracker,
    ) -> None:
        assert tracker.bump_rejection("BTCUSDT", "LONG") == 1
        assert tracker.bump_rejection("BTCUSDT", "LONG") == 2
        assert tracker.consecutive_rejections("BTCUSDT", "LONG") == 2
        assert tracker.consecutive_rejections("BTCUSDT", "SHORT") == 0

    def test_clear_rejections_only_resets_that_direction(
        self,
        tracker: SymbolStateTracker,
    ) -> None:
        tracker.bump_rejection("BTCUSDT", "LONG")
        tracker.bump_rejection("BTCUSDT", "SHORT")

        tracker.clear_rejections("BTCUSDT", "LONG")
        tracker.clear_rejections("BTCUSDT", "LONG")

        assert tracker.consecutive_rejections("BTCUSDT", "LONG") == 0
        assert tracker.consecutive_rejections("BTCUSDT", "SHORT") == 1

    def test_waits_count_and_clear_independently_of_rejections(
        self,
        tracker: SymbolStateTracker,
    ) -> None:
        tracker.bump_rejection("BTCUSDT", "LONG")
        assert tracker.bump_wait("BTCUSDT", "LONG") == 1
        assert tracker.bump_wait("BTCUSDT", "LONG") == 2

        tracker.clear_waits("BTCUSDT", "LONG")

        assert tracker.consecutive_waits("BTCUSDT", "LONG") == 0
        assert tracker.consecutive_rejections("BTCUSDT", "LONG") == 1


class TestSkipsAndGeometry:
    def test_clear_skip_suspension_resets_both_counters(
        self,
        tracker: SymbolStateTracker,
    ) -> None:
        tracker.bump_skip("BTCUSDT")
        assert tracker.bump_skip("BTCUSDT") == 2
        tracker.set_skip_eval_interval("BTCUSDT", 4)
        assert tracker.skip_eval_interval("BTCUSDT") == 4

        tracker.clear_skip_suspension("BTCUSDT")

        assert tracker.consecutive_skips("BTCUSDT") == 0
        assert tracker.skip_eval_interval("BTCUSDT") == 0

    def test_geometry_rejects_count_and_clear(
        self,
        tracker: SymbolStateTracker,
    ) -> None:
        assert tracker.bump_geometry_reject("BTCUSDT") == 1
        assert tracker.bump_geometry_reject("BTCUSDT") == 2
        assert tracker.geometry_rejects("ETHUSDT") == 0

        tracker.clear_geometry_rejects("BTCUSDT")

        assert tracker.geometry_rejects("BTCUSDT") == 0

    def test_state_schema_rejects_negative_counters(self) -> None:
        with pytest.raises(ValidationError):
            SymbolStateSchema.model_validate({"consecutive_skips": -1})
