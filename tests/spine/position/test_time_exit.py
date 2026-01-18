from datetime import UTC, datetime, timedelta

from kavzi_trader.spine.position.position_action_type import PositionActionType
from kavzi_trader.spine.position.time_exit import TimeExitChecker


def test_time_exit_triggers_after_max_hold(position_factory, monkeypatch) -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    opened_at = now - timedelta(hours=25)
    position = position_factory(opened_at=opened_at, updated_at=opened_at)

    def fake_now() -> datetime:
        return now

    monkeypatch.setattr(
        "kavzi_trader.spine.position.time_exit.utc_now",
        fake_now,
    )

    checker = TimeExitChecker()
    action = checker.evaluate(position)

    assert action is not None
    assert action.action == PositionActionType.FULL_EXIT


def test_time_exit_skips_when_within_window(position_factory, monkeypatch) -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    opened_at = now - timedelta(hours=5)
    position = position_factory(opened_at=opened_at, updated_at=opened_at)

    def fake_now() -> datetime:
        return now

    monkeypatch.setattr(
        "kavzi_trader.spine.position.time_exit.utc_now",
        fake_now,
    )

    checker = TimeExitChecker()
    action = checker.evaluate(position)

    assert action is None
