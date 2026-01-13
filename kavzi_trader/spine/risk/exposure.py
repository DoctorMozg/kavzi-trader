from kavzi_trader.spine.risk.config import RiskConfigSchema
from kavzi_trader.spine.risk.schemas import ExposureCheckSchema
from kavzi_trader.spine.state.schemas import PositionSchema


class ExposureLimiter:
    def __init__(self, config: RiskConfigSchema | None = None) -> None:
        self._config = config or RiskConfigSchema()

    def check_exposure(
        self,
        symbol: str,
        current_positions: list[PositionSchema],
    ) -> ExposureCheckSchema:
        position_count = len(current_positions)
        max_positions = self._config.max_positions

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

        return ExposureCheckSchema(
            is_allowed=True,
            current_position_count=position_count,
            max_positions=max_positions,
        )
