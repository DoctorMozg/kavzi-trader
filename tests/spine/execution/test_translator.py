from decimal import Decimal

import pytest

from kavzi_trader.api.common.models import OrderSide, OrderType, TimeInForce
from kavzi_trader.spine.execution.translator import (
    DecisionTranslator,
    OrderTranslationError,
)


def test_translator_builds_order(decision_message) -> None:
    translator = DecisionTranslator()

    request = translator.translate(decision_message)

    assert request.symbol == decision_message.symbol
    assert request.side == OrderSide.BUY
    assert request.order_type == OrderType.LIMIT
    assert request.quantity == decision_message.quantity
    assert request.price == decision_message.entry_price
    assert request.time_in_force == TimeInForce.GTC
    assert request.client_order_id == decision_message.decision_id


def test_translator_applies_override(decision_message) -> None:
    translator = DecisionTranslator()
    override = Decimal("2.5")

    request = translator.translate(decision_message, quantity_override=override)

    assert request.quantity == override


def test_translator_rejects_zero_quantity_override(decision_message) -> None:
    translator = DecisionTranslator()

    with pytest.raises(OrderTranslationError):
        translator.translate(decision_message, quantity_override=Decimal(0))


def test_translator_rejects_negative_quantity_override(decision_message) -> None:
    translator = DecisionTranslator()

    with pytest.raises(OrderTranslationError):
        translator.translate(decision_message, quantity_override=Decimal(-1))


def test_translator_rejects_none_quantity(decision_message) -> None:
    # Schema allows quantity=None (risk validator computes the final size);
    # the translator is the last guard that must refuse non-positive orders.
    decision_without_qty = decision_message.model_copy(update={"quantity": None})
    translator = DecisionTranslator()

    with pytest.raises(OrderTranslationError):
        translator.translate(decision_without_qty)
