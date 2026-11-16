import numpy as np
import pytest

from kavzi_trader.strategies.trend.turnover_buffer import TurnoverBuffer


@pytest.fixture
def buffer() -> TurnoverBuffer:
    return TurnoverBuffer(0.2)


class TestTurnoverBuffer:
    def test_small_moves_hold_and_large_ones_trade(
        self, buffer: TurnoverBuffer
    ) -> None:
        targets = np.array([[0.10], [0.11], [0.13], [0.0], [0.05], [-0.05]])

        held = buffer.apply(targets)

        # 0.11 is within 20% of 0.10; 0.13 is not; zero and a sign flip always trade.
        assert held[:, 0].tolist() == [0.10, 0.10, 0.13, 0.0, 0.05, -0.05]

    def test_symbols_are_buffered_independently(self, buffer: TurnoverBuffer) -> None:
        targets = np.array([[0.10, 0.10], [0.11, 0.20]])

        held = buffer.apply(targets)

        assert held[1].tolist() == [0.10, 0.20]

    def test_starts_flat_so_first_target_always_trades(
        self, buffer: TurnoverBuffer
    ) -> None:
        held = buffer.apply(np.array([[0.001]]))

        assert held[0, 0] == 0.001

    def test_rejects_negative_band(self) -> None:
        with pytest.raises(ValueError, match="band"):
            TurnoverBuffer(-0.1)
