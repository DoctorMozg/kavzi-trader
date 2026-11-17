import logging
from collections.abc import Collection

from kavzi_trader.domain.risk_config import RiskConfigSchema
from kavzi_trader.domain.state_schemas import PositionSchema
from kavzi_trader.spine.risk.schemas import ExposureCheckSchema

logger = logging.getLogger(__name__)


class ExposureLimiter:
    def __init__(self, config: RiskConfigSchema | None = None) -> None:
        self._config = config or RiskConfigSchema()

    def check_exposure(
        self,
        symbol: str,
        current_positions: list[PositionSchema],
        *,
        pending_symbols: Collection[str],
    ) -> ExposureCheckSchema:
        """Resting entry limits hold a slot: they can fill without another check."""
        open_symbols = {position.symbol for position in current_positions}
        resting = set(pending_symbols) - open_symbols
        position_count = len(current_positions) + len(resting)
        max_positions = self._config.max_positions

        logger.debug(
            "Exposure check: symbol=%s positions=%d/%d",
            symbol,
            position_count,
            max_positions,
        )

        if position_count >= max_positions:
            return ExposureCheckSchema(
                is_allowed=False,
                current_position_count=position_count,
                max_positions=max_positions,
                rejection_reason=f"Max positions reached ({position_count}/{max_positions})",  # noqa: E501
            )

        for position in current_positions:
            if position.symbol == symbol:
                return ExposureCheckSchema(
                    is_allowed=False,
                    current_position_count=position_count,
                    max_positions=max_positions,
                    rejection_reason=f"Already have position in {symbol}",
                )

        if symbol in resting:
            return ExposureCheckSchema(
                is_allowed=False,
                current_position_count=position_count,
                max_positions=max_positions,
                rejection_reason=f"Pending entry already resting for {symbol}",
            )

        return ExposureCheckSchema(
            is_allowed=True,
            current_position_count=position_count,
            max_positions=max_positions,
        )
