from pydantic import BaseModel, ConfigDict


class FundingXsLegsSchema(BaseModel):
    """Symbols to hold long (lowest funding) and short (highest funding)."""

    longs: list[str]
    shorts: list[str]

    model_config = ConfigDict(frozen=True)
