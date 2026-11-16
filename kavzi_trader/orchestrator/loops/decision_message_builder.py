import logging
from collections.abc import Callable
from decimal import Decimal
from typing import Literal, cast
from uuid import uuid4

from kavzi_trader.brain.geometry.schemas import TradeGeometrySchema
from kavzi_trader.brain.schemas.dependencies import TradingDependenciesSchema
from kavzi_trader.domain.state_schemas import PositionManagementConfigSchema
from kavzi_trader.domain.trade_decision import TradeDecisionSchema
from kavzi_trader.strategies.bracket_intent_schema import BracketIntentSchema

logger = logging.getLogger(__name__)

_DECISION_TTL_MS = 300_000


class DecisionMessageBuilder:
    """Turns a Trader decision into the message handed from Brain to Spine."""

    def __init__(
        self,
        position_management: PositionManagementConfigSchema,
        on_missing_geometry: Callable[[str], object],
    ) -> None:
        self._position_management = position_management
        self._on_missing_geometry = on_missing_geometry

    def build(
        self,
        trader: TradeDecisionSchema,
        deps: TradingDependenciesSchema,
        snapshot_at_ms: int,
        geometry: TradeGeometrySchema | None = None,
        size_multiplier: Decimal = Decimal(1),
    ) -> BracketIntentSchema | None:
        action = trader.action
        # The router computes geometry for every LONG/SHORT, so a missing one
        # is a pipeline defect: fail loudly instead of fabricating prices.
        if action in {"LONG", "SHORT"} and geometry is None:
            logger.error(
                "Trader %s decision for %s arrived without computed"
                " geometry; refusing to enqueue",
                action,
                deps.symbol,
                extra={"symbol": deps.symbol, "action": action},
            )
            self._on_missing_geometry(deps.symbol)
            return None

        # WAIT is filtered upstream, so only LONG/SHORT/CLOSE reach this point.
        typed_action = cast("Literal['LONG', 'SHORT', 'CLOSE']", action)

        # CLOSE has no geometry; the execution layer only needs a price reference.
        if geometry is not None:
            entry_price = geometry.entry
            stop_loss = geometry.stop_loss
            take_profit = geometry.take_profit
        else:
            entry_price = deps.current_price
            stop_loss = entry_price
            take_profit = entry_price
        atr = deps.indicators.atr_14 or Decimal(0)

        return BracketIntentSchema(
            decision_id=str(uuid4()),
            symbol=deps.symbol,
            action=typed_action,
            entry_tactic=trader.entry_tactic or "IMMEDIATE",
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            quantity=None,
            reasoning=trader.reasoning,
            raw_confidence=trader.confidence,
            calibrated_confidence=trader.confidence,
            volatility_regime=deps.volatility_regime,
            position_management=self._position_management,
            created_at_ms=snapshot_at_ms,
            expires_at_ms=snapshot_at_ms + _DECISION_TTL_MS,
            current_atr=atr,
            atr_history=deps.atr_history,
            leverage=deps.leverage,
            symbol_tier=deps.symbol_tier,
            size_multiplier=size_multiplier,
        )
