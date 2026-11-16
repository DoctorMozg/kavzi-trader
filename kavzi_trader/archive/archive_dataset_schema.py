from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class ArchiveDatasetSchema(BaseModel):
    """One data.binance.vision USD-M dataset and how to store its rows."""

    model_config = ConfigDict(frozen=True)

    # Directory name in the archive, e.g. "klines" or "fundingRate".
    name: str
    # Kline interval for the kline-shaped datasets; funding has none.
    interval: str | None = None
    # Stored column names; positional unless source_columns names them.
    columns: Annotated[list[str], Field(min_length=2)]
    # Header names to keep, in stored-column order, for CSVs that always have one.
    source_columns: list[str] | None = None
    # Daily-only datasets; the store still keeps one file per month.
    daily: bool = False

    @property
    def prefix(self) -> str:
        cadence = "daily" if self.daily else "monthly"
        return f"data/futures/um/{cadence}/"

    def file_stem(self, symbol: str, period: str) -> str:
        if self.interval is not None:
            return f"{symbol}-{self.interval}-{period}"
        return f"{symbol}-{self.name}-{period}"

    def symbol_dir(self, symbol: str) -> str:
        if self.interval is not None:
            return f"{self.name}/{symbol}/{self.interval}"
        return f"{self.name}/{symbol}"
