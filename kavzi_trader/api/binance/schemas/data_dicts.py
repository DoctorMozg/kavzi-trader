from typing import Any, NotRequired, TypedDict


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


class MarkPriceData(TypedDict):
    """Type definition for Futures mark price stream data."""

    e: str  # Event type: "markPriceUpdate"
    E: int  # Event time (ms)
    s: str  # Symbol
    p: str  # Mark price
    i: str  # Index price
    P: str  # Estimated settle price (only for delivery)
    r: str  # Funding rate
    T: int  # Next funding time (ms)


class ForceOrderData(TypedDict):
    """Type definition for Futures liquidation order stream data."""

    e: str  # Event type: "forceOrder"
    E: int  # Event time (ms)
    o: dict[str, Any]  # Order data containing: s, S, o, f, q, p, ap, X, l, z, T


# ------------------------------------------------------------------
# Futures REST API response shapes (used by paper exchange + callers)
# ------------------------------------------------------------------


class AccountPositionDict(TypedDict):
    """Single position entry in account info response."""

    symbol: str
    positionAmt: str
    entryPrice: str
    leverage: str
    unrealizedProfit: str
    marginType: str
    isolatedMargin: str
    positionSide: str


class AccountInfoDict(TypedDict):
    """Response from GET /fapi/v2/account."""

    totalWalletBalance: str
    availableBalance: str
    totalUnrealizedProfit: str
    totalInitialMargin: str
    totalMaintMargin: str
    positions: list[AccountPositionDict]


class AssetBalanceDict(TypedDict):
    """Response from futures asset balance query."""

    asset: str
    balance: str
    availableBalance: str
    crossUnPnl: NotRequired[str]


class LeverageChangeDict(TypedDict):
    """Response from POST /fapi/v1/leverage."""

    leverage: int
    symbol: str
    maxNotionalValue: str


class MarginTypeChangeDict(TypedDict):
    """Response from POST /fapi/v1/marginType."""

    code: int
    msg: str


class PositionInfoDict(TypedDict):
    """Single entry from GET /fapi/v2/positionRisk."""

    symbol: str
    positionAmt: str
    entryPrice: str
    markPrice: str
    unRealizedProfit: str
    liquidationPrice: str
    leverage: str
    marginType: str
    isolatedMargin: str
    positionSide: str


class LeverageBracketEntryDict(TypedDict):
    """Single bracket entry in leverage bracket response."""

    bracket: int
    initialLeverage: int
    notionalCap: int
    notionalFloor: int
    maintMarginRatio: float


class LeverageBracketDict(TypedDict):
    """Response entry from GET /fapi/v1/leverageBracket."""

    symbol: str
    brackets: list[LeverageBracketEntryDict]
