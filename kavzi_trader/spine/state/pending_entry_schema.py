from pydantic import BaseModel, ConfigDict


class PendingEntrySchema(BaseModel):
    """A resting PULLBACK entry limit awaiting fill or expiry.

    ``decision_json`` is the serialized ``DecisionMessageSchema`` that placed
    the order — stored as a string to keep this state schema free of an
    import cycle with the execution layer. The engine re-parses it to open
    and protect the position once the limit fills.
    """

    order_id: str
    symbol: str
    decision_json: str
    expires_at_ms: int

    model_config = ConfigDict(frozen=True)
