from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from kavzi_trader.spine.filters.liquidity_period import LiquidityPeriod
from kavzi_trader.spine.filters.liquidity_session_schema import LiquiditySessionSchema


def _default_liquidity_sessions() -> list[LiquiditySessionSchema]:
    return [
        LiquiditySessionSchema(
            period=LiquidityPeriod.HIGH,
            start_hour=13,
            end_hour=21,
        ),
        LiquiditySessionSchema(
            period=LiquidityPeriod.MEDIUM,
            start_hour=7,
            end_hour=13,
        ),
        LiquiditySessionSchema(
            period=LiquidityPeriod.MEDIUM,
            start_hour=21,
            end_hour=1,
        ),
        LiquiditySessionSchema(
            period=LiquidityPeriod.LOW,
            start_hour=1,
            end_hour=7,
        ),
    ]


def _default_liquidity_multipliers() -> dict[str, Decimal]:
    return {
        LiquidityPeriod.HIGH.value: Decimal("1.0"),
        LiquidityPeriod.MEDIUM.value: Decimal("0.8"),
        LiquidityPeriod.LOW.value: Decimal("0.5"),
    }


def _default_correlated_pairs() -> dict[str, list[str]]:
    return {
        "BTCUSDT": ["ETHUSDT"],
        "ETHUSDT": ["BTCUSDT"],
    }


class FilterConfigSchema(BaseModel):
    """Holds tuning parameters for the pre-trade filter chain."""

    liquidity_sessions: Annotated[
        list[LiquiditySessionSchema],
        Field(default_factory=_default_liquidity_sessions),
    ] = Field(default_factory=_default_liquidity_sessions)
    liquidity_multipliers: Annotated[
        dict[str, Decimal],
        Field(default_factory=_default_liquidity_multipliers),
    ] = Field(default_factory=_default_liquidity_multipliers)
    weekend_size_multiplier: Annotated[
        Decimal,
        Field(default=Decimal("0.5")),
    ] = Decimal("0.5")
    sunday_after_20utc_multiplier: Annotated[
        Decimal,
        Field(default=Decimal("0.8")),
    ] = Decimal("0.8")

    crowded_long_zscore: Annotated[
        Decimal,
        Field(default=Decimal("2.0")),
    ] = Decimal("2.0")
    crowded_short_zscore: Annotated[
        Decimal,
        Field(default=Decimal("-2.0")),
    ] = Decimal("-2.0")

    min_body_atr_ratio: Annotated[
        Decimal,
        Field(default=Decimal("0.3")),
    ] = Decimal("0.3")

    correlated_pairs: Annotated[
        dict[str, list[str]],
        Field(default_factory=_default_correlated_pairs),
    ] = Field(default_factory=_default_correlated_pairs)
    max_correlated_exposure: Annotated[
        Decimal,
        Field(default=Decimal("0.5")),
    ] = Decimal("0.5")

    model_config = ConfigDict(frozen=True)
