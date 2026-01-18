from pydantic import BaseModel, ConfigDict

from kavzi_trader.brain.context.formatters import dump_json, dump_optional_json
from kavzi_trader.brain.context.market_snapshot import MarketSnapshotSchema
from kavzi_trader.brain.schemas.dependencies import (
    AnalystDependenciesSchema,
    ScoutDependenciesSchema,
    TradingDependenciesSchema,
)


class ContextBuilder(BaseModel):
    """
    Builds prompt context payloads from dependency schemas.
    """

    model_config = ConfigDict(frozen=True)

    def build_scout_context(self, deps: ScoutDependenciesSchema) -> dict[str, str]:
        snapshot = MarketSnapshotSchema(
            symbol=deps.symbol,
            current_price=deps.current_price,
            timeframe=deps.timeframe,
            recent_candles=deps.recent_candles,
            indicators=deps.indicators,
            volatility_regime=deps.volatility_regime,
        )
        return {"market_snapshot_json": dump_json(snapshot)}

    def build_analyst_context(
        self,
        deps: AnalystDependenciesSchema,
    ) -> dict[str, str | None]:
        snapshot = MarketSnapshotSchema(
            symbol=deps.symbol,
            current_price=deps.current_price,
            timeframe=deps.timeframe,
            recent_candles=deps.recent_candles,
            indicators=deps.indicators,
            volatility_regime=deps.volatility_regime,
        )
        return {
            "market_snapshot_json": dump_json(snapshot),
            "order_flow_json": dump_optional_json(deps.order_flow),
            "algorithm_confluence_json": dump_json(deps.algorithm_confluence),
        }

    def build_trader_context(
        self,
        deps: TradingDependenciesSchema,
    ) -> dict[str, str | None]:
        snapshot = MarketSnapshotSchema(
            symbol=deps.symbol,
            current_price=deps.current_price,
            timeframe=deps.timeframe,
            recent_candles=deps.recent_candles,
            indicators=deps.indicators,
            volatility_regime=deps.volatility_regime,
        )
        return {
            "market_snapshot_json": dump_json(snapshot),
            "order_flow_json": dump_optional_json(deps.order_flow),
            "algorithm_confluence_json": dump_json(deps.algorithm_confluence),
            "account_state_json": dump_json(deps.account_state),
        }
