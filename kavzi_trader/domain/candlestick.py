from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class CandlestickSchema(BaseModel):
    """Candlestick/kline data."""

    open_time: datetime
    open_price: Decimal
    high_price: Decimal
    low_price: Decimal
    close_price: Decimal
    volume: Decimal
    close_time: datetime
    quote_volume: Decimal
    trades_count: int
    taker_buy_base_volume: Decimal
    taker_buy_quote_volume: Decimal
    interval: str | None = None
    symbol: str | None = None

    model_config = ConfigDict(frozen=True)
