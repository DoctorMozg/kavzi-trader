

from typing import Any, TypedDict


class KlineData(TypedDict):
    """Type definition for kline message data."""

    e: str  # Event type
    E: int  # Event time
    s: str  # Symbol
    k: dict[str, Any]  # Kline data


class TradeData(TypedDict):
    """Type definition for trade message data."""

    e: str  # Event type
    E: int  # Event time
    s: str  # Symbol
    t: int  # Trade ID
    p: str  # Price
    q: str  # Quantity
    b: int  # Buyer order ID
    a: int  # Seller order ID
    T: int  # Trade time
    m: bool  # Is buyer the market maker
    M: bool  # Ignore


class TickerData(TypedDict):
    """Type definition for ticker message data."""

    e: str  # Event type
    E: int  # Event time
    s: str  # Symbol
    p: str  # Price change
    P: str  # Price change percent
    w: str  # Weighted average price
    x: str  # First trade price
    c: str  # Last price
    Q: str  # Last quantity
    b: str  # Best bid price
    B: str  # Best bid quantity
    a: str  # Best ask price
    A: str  # Best ask quantity
    o: str  # Open price
    h: str  # High price
    l: str  # Low price ,  # noqa: E741
    v: str  # Total traded base asset volume
    q: str  # Total traded quote asset volume
    O: int  # Statistics open time # noqa: E741
    C: int  # Statistics close time
    F: int  # First trade ID
    L: int  # Last trade ID
    n: int  # Total number of trades