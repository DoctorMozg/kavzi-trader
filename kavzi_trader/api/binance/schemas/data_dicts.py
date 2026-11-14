from typing import NotRequired, TypedDict


class KlineBodyData(TypedDict):
    """Inner `k` object of a kline stream message."""

    t: int  # Kline start time
    T: int  # Kline close time
    s: str  # Symbol
    i: str  # Interval
    f: int  # First trade ID
    L: int  # Last trade ID
    o: str  # Open price
    c: str  # Close price
    h: str  # High price
    l: str  # Low price # noqa: E741
    v: str  # Base asset volume
    n: int  # Number of trades
    x: bool  # Is this kline closed
    q: str  # Quote asset volume
    V: str  # Taker buy base asset volume
    Q: str  # Taker buy quote asset volume
    B: str  # Ignore


class KlineData(TypedDict):
    """Type definition for kline message data."""

    e: str  # Event type
    E: int  # Event time
    s: str  # Symbol
    k: KlineBodyData  # Kline data


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


class DepthData(TypedDict):
    """Type definition for Futures partial book depth stream data."""

    e: str  # Event type: "depthUpdate"
    E: int  # Event time (ms)
    T: int  # Transaction time (ms)
    s: str  # Symbol
    U: int  # First update ID
    u: int  # Final update ID
    pu: int  # Final update ID of the previous stream message
    b: list[list[str]]  # Bids as [price, quantity]
    a: list[list[str]]  # Asks as [price, quantity]


class ForceOrderBodyData(TypedDict):
    """Inner `o` object of a forceOrder stream message."""

    s: str  # Symbol
    S: str  # Side
    o: str  # Order type
    f: str  # Time in force
    q: str  # Original quantity
    p: str  # Price
    ap: str  # Average price
    X: str  # Order status
    l: str  # Last filled quantity # noqa: E741
    z: str  # Filled accumulated quantity
    T: int  # Trade time


class ForceOrderData(TypedDict):
    """Type definition for Futures liquidation order stream data."""

    e: str  # Event type: "forceOrder"
    E: int  # Event time (ms)
    o: ForceOrderBodyData  # Order data


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
    cum: float


class LeverageBracketDict(TypedDict):
    """Response entry from GET /fapi/v1/leverageBracket."""

    symbol: str
    brackets: list[LeverageBracketEntryDict]


class FundingRateDict(TypedDict):
    """Single entry from GET /fapi/v1/fundingRate."""

    symbol: str
    fundingRate: str
    fundingTime: int
    markPrice: NotRequired[str]


class OpenInterestHistDict(TypedDict):
    """Single entry from GET /futures/data/openInterestHist."""

    symbol: str
    sumOpenInterest: str
    sumOpenInterestValue: str
    timestamp: int


class LongShortRatioDict(TypedDict):
    """Single entry from GET /futures/data/globalLongShortAccountRatio."""

    symbol: str
    longShortRatio: str
    longAccount: str
    shortAccount: str
    timestamp: int


class OpenInterestDict(TypedDict):
    """Response from GET /fapi/v1/openInterest."""

    symbol: str
    openInterest: str
    time: int


class AvgPriceDict(TypedDict):
    """Response from GET /api/v3/avgPrice."""

    mins: int
    price: str
    closeTime: int


class OrderFillDict(TypedDict):
    """Single fill inside an order response."""

    price: str
    qty: str
    commission: str
    commissionAsset: str
    tradeId: NotRequired[int]


class FuturesOrderDict(TypedDict, total=False):
    """Order payload from the futures order endpoints.

    Binance omits many fields depending on order type and endpoint, so
    everything but the identifiers is optional.
    """

    symbol: str
    orderId: int
    clientOrderId: str
    transactTime: int
    price: str
    origQty: str
    executedQty: str
    status: str
    timeInForce: str
    type: str
    side: str
    fills: list[OrderFillDict]
    stopPrice: str
    avgPrice: str
    icebergQty: str
    time: int
    updateTime: int
    isWorking: bool
    origQuoteOrderQty: str
    reduceOnly: bool
    positionSide: str
    closePosition: bool
