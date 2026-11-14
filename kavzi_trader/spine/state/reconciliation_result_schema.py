from pydantic import BaseModel, ConfigDict


class ReconciliationResultSchema(BaseModel):
    success: bool
    discrepancies: list[str]
    positions_synced: int = 0
    orders_synced: int = 0
    orders_removed: int = 0

    model_config = ConfigDict(frozen=True)
