import pytest

from kavzi_trader.brain.context.confluence_trimmer import (
    ConfluenceBlockDict,
    side_trim_confluence,
)


def _block(score: int) -> ConfluenceBlockDict:
    return ConfluenceBlockDict(
        ema_alignment=True,
        rsi_favorable=False,
        volume_above_average=False,
        price_at_bollinger=False,
        funding_favorable=False,
        oi_supports_direction=False,
        oi_funding_divergence=False,
        volume_spike=False,
        score=score,
    )


class TestSideTrimConfluence:
    def test_long_drops_the_short_block(self) -> None:
        long_block, short_block = _block(5), _block(2)

        assert side_trim_confluence(long_block, short_block, "LONG") == (
            long_block,
            None,
        )

    def test_short_drops_the_long_block(self) -> None:
        long_block, short_block = _block(5), _block(2)

        assert side_trim_confluence(long_block, short_block, "SHORT") == (
            None,
            short_block,
        )

    @pytest.mark.parametrize("side", ["NEUTRAL", "", "long"])
    def test_anything_else_keeps_both_blocks(self, side: str) -> None:
        long_block, short_block = _block(5), _block(2)

        assert side_trim_confluence(long_block, short_block, side) == (
            long_block,
            short_block,
        )
