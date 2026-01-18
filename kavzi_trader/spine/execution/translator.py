from decimal import Decimal

from kavzi_trader.api.common.models import (
    OrderSide,
    OrderType,
    TimeInForce,
)
from kavzi_trader.spine.execution.decision_message_schema import DecisionMessageSchema
from kavzi_trader.spine.execution.order_request_schema import OrderRequestSchema


class DecisionTranslator:
    """Converts decision payloads into exchange order requests."""

    def translate(
        self,
        decision: DecisionMessageSchema,
        quantity_override: Decimal | None = None,
    ) -> OrderRequestSchema:
        side = OrderSide.BUY if decision.action == "BUY" else OrderSide.SELL
        quantity = (
            quantity_override if quantity_override is not None else decision.quantity
        )

        return OrderRequestSchema(
            symbol=decision.symbol,
            side=side,
            order_type=OrderType.LIMIT,
            quantity=quantity,
            price=decision.entry_price,
            time_in_force=TimeInForce.GTC,
            stop_price=None,
            client_order_id=decision.decision_id,
        )
