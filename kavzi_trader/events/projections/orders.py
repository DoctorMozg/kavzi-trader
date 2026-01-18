from kavzi_trader.events.event_schema import EventSchema


class OrdersProjection:
    """Materialized view of order status by order id."""

    def __init__(self) -> None:
        self._orders: dict[str, dict[str, object | None]] = {}

    def apply(self, event: EventSchema) -> None:
        if event.aggregate_type != "orders":
            return
        self._orders[event.aggregate_id] = dict(event.data)

    def snapshot(self) -> dict[str, dict[str, object | None]]:
        return dict(self._orders)
