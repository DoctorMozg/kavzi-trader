from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class ArchiveDatasetSchema(BaseModel):
    """One monthly data.binance.vision USD-M dataset and how to store its rows."""

    model_config = ConfigDict(frozen=True)

    # Directory name in the archive, e.g. "klines" or "fundingRate".
    name: str
    # Kline interval for the kline-shaped datasets; funding has none.
    interval: str | None = None
    # Stored column names, in the archive CSV's column order.
    columns: Annotated[list[str], Field(min_length=2)]

    def file_stem(self, symbol: str, month: str) -> str:
        if self.interval is not None:
            return f"{symbol}-{self.interval}-{month}"
        return f"{symbol}-{self.name}-{month}"

    def symbol_dir(self, symbol: str) -> str:
        if self.interval is not None:
            return f"{self.name}/{symbol}/{self.interval}"
        return f"{self.name}/{symbol}"
