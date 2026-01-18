# Spine Implementation Details

## Overview

The Spine is KavziTrader's deterministic execution layer. It handles all real-time, latency-sensitive operations including market data ingestion, order execution, dynamic risk management, and active position management. This document details the implementation specifics, event flows, and library choices.

## Library Stack

| Component | Library | Purpose |
|-----------|---------|---------|
| Async Runtime | `asyncio` | Event loop, coroutines |
| WebSocket Client | `python-binance` (AsyncClient) | Binance WebSocket streams |
| REST Client | `python-binance` (AsyncClient) | Binance REST API |
| Message Queue | `redis-py` (async) | Inter-component messaging |
| State Persistence | `redis-py` (async) | Fast state read/write |
| Event Store | `asyncpg` + `SQLAlchemy` | PostgreSQL event persistence |
| Data Validation | `pydantic` v2 | Schema validation |
| Serialization | `json` (stdlib) | JSON encode/decode |
| Logging | `commons.logging` | Application logging (existing) |

## Event Flow Architecture

### High-Level Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           BINANCE EXCHANGE                               │
└───────────┬─────────────────────────────────────┬───────────────────────┘
            │ WebSocket                           │ REST API
            ▼                                     ▲
┌───────────────────────┐                ┌────────────────────┐
│   WEBSOCKET MANAGER   │                │   ORDER EXECUTOR   │
│   (Data Ingest Loop)  │                │  (Execution Loop)  │
└───────────┬───────────┘                └────────▲───────────┘
            │                                     │
            ▼                                     │
┌───────────────────────┐                ┌────────┴───────────┐
│    STREAM HANDLERS    │                │  DYNAMIC RISK      │
│  (Klines, Depth, etc) │                │    VALIDATOR       │
└───────────┬───────────┘                └────────▲───────────┘
            │                                     │
            ▼                                     │
┌───────────────────────┐                ┌────────┴───────────┐
│   ORDER FLOW FETCHER  │                │ POSITION MANAGER   │
│  (Funding, OI, L/S)   │                │ (Trailing, Scaling)│
└───────────┬───────────┘                └────────▲───────────┘
            │                                     │
            ▼                                     │
┌───────────────────────────────────────────────────────────────────────┐
│                        REDIS MESSAGE QUEUES                            │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────┐   │
│  │ market_data:    │  │ decisions:      │  │ executions:         │   │
│  │   klines        │  │   pending       │  │   completed         │   │
│  │   depth         │  │                 │  │   failed            │   │
│  │   order_flow    │  │                 │  │                     │   │
│  └────────┬────────┘  └────────▲────────┘  └─────────────────────┘   │
└───────────┼────────────────────┼─────────────────────────────────────┘
            │                    │
            ▼                    │
┌───────────────────────┐        │
│    STATE MANAGER      │        │
│  (Positions, Orders)  │        │
└───────────┬───────────┘        │
            │                    │
            ▼                    │
┌───────────────────────┐        │
│   TRIGGER ENGINE      │────────┘
│  (Candle Close, etc)  │
└───────────────────────┘
            │
            ▼
     [To Brain/LLM]
```

## Redis Queue Schemas

### Queue Names and Purposes

| Queue | Type | Purpose | TTL |
|-------|------|---------|-----|
| `kt:market:klines:{symbol}` | Stream | Kline updates | 1 hour |
| `kt:market:depth:{symbol}` | Hash | Order book snapshot | None |
| `kt:market:trades:{symbol}` | Stream | Recent trades | 1 hour |
| `kt:market:orderflow:{symbol}` | Hash | Order flow data | None |
| `kt:decisions:pending` | List | LLM decisions awaiting execution | None |
| `kt:executions:log` | Stream | Execution results | 24 hours |
| `kt:state:positions` | Hash | Current positions | None |
| `kt:state:orders` | Hash | Open orders | None |
| `kt:state:account` | Hash | Account balances | None |
| `kt:triggers:candle_close` | Pub/Sub | Candle close notifications | N/A |
| `kt:position:updates` | Pub/Sub | Position management triggers | N/A |

### Message Schemas

#### Market Data Message

```python
class MarketDataMessage(BaseModel):
    msg_type: Literal["kline", "depth", "trade"]
    symbol: str
    timestamp_ms: int
    data: dict
```

#### Order Flow Message

```python
class OrderFlowMessage(BaseModel):
    symbol: str
    timestamp_ms: int
    funding_rate: float
    funding_rate_zscore: float
    open_interest: float
    oi_change_1h_percent: float
    oi_change_24h_percent: float
    long_short_ratio: float
    liquidation_levels_above: list[float]
    liquidation_levels_below: list[float]
```

#### Decision Message (Extended)

```python
class DecisionMessage(BaseModel):
    decision_id: str
    symbol: str
    action: Literal["BUY", "SELL", "CLOSE"]
    entry_price: float
    stop_loss: float
    take_profit: float
    quantity: float
    raw_confidence: float
    calibrated_confidence: float
    volatility_regime: Literal["LOW", "NORMAL", "HIGH", "EXTREME"]
    position_management: PositionManagementConfig
    created_at_ms: int
    expires_at_ms: int
```

#### Position Management Config

```python
class PositionManagementConfig(BaseModel):
    trailing_stop_atr_multiplier: float = 1.5
    break_even_trigger_atr: float = 1.0
    partial_exit_at_percent: float = 0.5
    partial_exit_size: float = 0.3
    max_hold_time_hours: int = 24
    scale_in_allowed: bool = False
    scale_in_max_multiplier: float = 1.5
```

#### Execution Result Message

```python
class ExecutionResultMessage(BaseModel):
    decision_id: str
    order_id: str | None
    status: Literal["FILLED", "PARTIAL", "REJECTED", "EXPIRED"]
    executed_qty: float
    executed_price: float
    error_message: str | None
    timestamp_ms: int
```

## Component Implementation

### 1. Order Flow Fetcher

Periodically fetches order flow data from Binance Futures API.

> **Note**: The underlying API methods (`get_funding_rate()`, `get_open_interest()`,
> `get_long_short_ratio()`) and analysis calculators (`calculate_funding_zscore()`,
> `calculate_oi_momentum()`, `OrderFlowCalculator`) are implemented in Phase 1.5.
> This orchestration layer uses those components.

```python
class OrderFlowFetcher:
    def __init__(
        self,
        client: BinanceClient,
        redis: Redis,
        symbols: list[str],
        fetch_interval_s: float = 60.0
    ):
        self.client = client
        self.redis = redis
        self.symbols = symbols
        self.fetch_interval_s = fetch_interval_s
        self.funding_history: dict[str, deque] = {}

    async def start(self):
        while True:
            await self._fetch_all_symbols()
            await asyncio.sleep(self.fetch_interval_s)

    async def _fetch_all_symbols(self):
        await asyncio.gather(*[
            self._fetch_symbol(symbol) for symbol in self.symbols
        ])

    async def _fetch_symbol(self, symbol: str):
        funding = await self.client.get_funding_rate(symbol)
        oi = await self.client.get_open_interest(symbol)
        ls_ratio = await self.client.get_long_short_ratio(symbol)

        zscore = self._calculate_funding_zscore(symbol, funding.rate)
        oi_changes = await self._calculate_oi_changes(symbol, oi.value)
        liquidations = self._estimate_liquidation_levels(oi, funding)

        message = OrderFlowMessage(
            symbol=symbol,
            timestamp_ms=int(time.time() * 1000),
            funding_rate=funding.rate,
            funding_rate_zscore=zscore,
            open_interest=oi.value,
            oi_change_1h_percent=oi_changes["1h"],
            oi_change_24h_percent=oi_changes["24h"],
            long_short_ratio=ls_ratio.value,
            liquidation_levels_above=liquidations["above"],
            liquidation_levels_below=liquidations["below"]
        )

        await self.redis.hset(
            f"kt:market:orderflow:{symbol}",
            mapping=message.model_dump()
        )
```

### 2. WebSocket Manager

Manages all Binance WebSocket connections with auto-reconnect.

```python
class WebSocketManager:
    def __init__(
        self,
        client: BinanceAPIClient,
        redis: Redis,
        symbols: list[str],
        handlers: dict[str, StreamHandler]
    ):
        self.client = client
        self.redis = redis
        self.symbols = symbols
        self.handlers = handlers
        self.connections: dict[str, WebSocket] = {}
        self.reconnect_delay_s = 1.0
        self.max_reconnect_delay_s = 60.0

    async def start(self):
        await asyncio.gather(*[
            self._run_stream(symbol) for symbol in self.symbols
        ])

    async def _run_stream(self, symbol: str):
        while True:
            try:
                async with self._connect(symbol) as ws:
                    self.reconnect_delay_s = 1.0
                    await self._handle_messages(ws, symbol)
            except ConnectionClosed:
                await self._handle_reconnect(symbol)

    async def _handle_reconnect(self, symbol: str):
        await asyncio.sleep(self.reconnect_delay_s)
        self.reconnect_delay_s = min(
            self.reconnect_delay_s * 2,
            self.max_reconnect_delay_s
        )
```

### 3. Volatility Regime Detector

Determines current market volatility for dynamic risk adjustment.

```python
class VolatilityRegimeDetector:
    def __init__(self, atr_period: int = 14, lookback_periods: int = 100):
        self.atr_period = atr_period
        self.lookback_periods = lookback_periods

    def detect_regime(
        self,
        candles: list[CandleSchema],
        current_atr: float
    ) -> Literal["LOW", "NORMAL", "HIGH", "EXTREME"]:
        historical_atrs = self._calculate_historical_atrs(candles)

        if len(historical_atrs) < self.lookback_periods:
            return "NORMAL"

        mean_atr = statistics.mean(historical_atrs)
        std_atr = statistics.stdev(historical_atrs)

        zscore = (current_atr - mean_atr) / std_atr if std_atr > 0 else 0

        if zscore < -1.0:
            return "LOW"
        elif zscore < 1.0:
            return "NORMAL"
        elif zscore < 2.0:
            return "HIGH"
        else:
            return "EXTREME"

    def get_staleness_threshold_ms(
        self,
        regime: Literal["LOW", "NORMAL", "HIGH", "EXTREME"]
    ) -> int:
        thresholds = {
            "LOW": 60_000,
            "NORMAL": 30_000,
            "HIGH": 15_000,
            "EXTREME": 5_000
        }
        return thresholds[regime]
```

### 4. Dynamic Risk Validator ✅ IMPLEMENTED

Volatility-aware risk validation before order execution. Located in `spine/risk/`.

**Implemented Components:**

| Component | File | Purpose |
|-----------|------|---------|
| `RiskConfigSchema` | `config.py` | Configurable thresholds |
| `VolatilityRegimeDetector` | `volatility.py` | ATR Z-score regime classification |
| `PositionSizer` | `position_sizer.py` | ATR-based position sizing |
| `ExposureLimiter` | `exposure.py` | Max positions enforcement |
| `DynamicRiskValidator` | `validator.py` | Orchestrates all validations |

```python
class DynamicRiskValidator:
    def __init__(self, config: RiskConfigSchema | None = None) -> None:
        self._config = config or RiskConfigSchema()
        self._volatility_detector = VolatilityRegimeDetector(self._config)
        self._position_sizer = PositionSizer(self._config)
        self._exposure_limiter = ExposureLimiter(self._config)

    async def validate_trade(
        self,
        symbol: str,
        side: Literal["LONG", "SHORT"],
        entry_price: Decimal,
        stop_loss: Decimal,
        take_profit: Decimal,
        current_atr: Decimal,
        atr_history: list[Decimal],
        state_manager: StateManager,
    ) -> RiskValidationResultSchema:
        # Validates: drawdown, exposure, volatility regime, SL/TP, R:R ratio
        # Returns recommended position size with adjustments
        ...
```

**Volatility Regime Classification:**

| ATR Z-Score | Regime | Size Multiplier | Tradeable |
|-------------|--------|-----------------|-----------|
| < -1.0 | LOW | 0% | No |
| -1.0 to 1.0 | NORMAL | 100% | Yes |
| 1.0 to 2.0 | HIGH | 50% | Yes |
| > 2.0 | EXTREME | 0% | No |

**Validation Checks:**

| Check | Threshold | Action |
|-------|-----------|--------|
| Drawdown | > 5% | Reject + close all flag |
| Drawdown | > 3% | Reject (no new positions) |
| Max positions | >= 2 | Reject |
| Stop loss | < 0.5 ATR | Reject (too tight) |
| Stop loss | > 3.0 ATR | Reject (too wide) |
| R:R ratio | < 1.5 | Reject |
| Volatility | LOW/EXTREME | Reject |

### 4.5 Pre-Trade Filters ✅ IMPLEMENTED

Algorithmic pre-filters that run before LLM decisions. Located in `spine/filters/`.

**Implemented Components:**

| Component | File | Purpose |
|-----------|------|---------|
| `FilterConfigSchema` | `config.py` | Filter tuning and thresholds |
| `LiquidityFilter` | `liquidity.py` | Session-based size adjustment |
| `NewsEventFilter` | `news.py` | Block around event windows |
| `FundingRateFilter` | `funding.py` | Block crowded funding |
| `CorrelationFilter` | `correlation.py` | Reduce correlated exposure |
| `MinimumMovementFilter` | `movement.py` | Skip low-body candles |
| `ConfluenceCalculator` | `confluence.py` | Rule-based scoring |
| `PreTradeFilterChain` | `chain.py` | Ordered filter orchestration |

**Filter Order:**

| Order | Filter | Action |
|-------|--------|--------|
| 1 | Volatility | Skip if EXTREME or LOW regime |
| 2 | News | Skip during major event window |
| 3 | Funding | Block trades against extreme funding |
| 4 | Movement | Skip doji/no-body candle |
| 5 | Position | Skip if max positions reached |
| 6 | Liquidity | Adjust size (weekend/off-hours) |
| 7 | Correlation | Reduce size for correlated exposure |

### 5. Position Manager

Active position management with trailing stops, partial exits, and scaling.

```python
class PositionManager:
    def __init__(
        self,
        state_manager: StateManager,
        order_executor: OrderExecutor,
        atr_calculator: ATRCalculator
    ):
        self.state = state_manager
        self.executor = order_executor
        self.atr = atr_calculator
        self.check_interval_s = 5.0

    async def start(self):
        while True:
            await self._check_all_positions()
            await asyncio.sleep(self.check_interval_s)

    async def _check_all_positions(self):
        positions = await self.state.get_all_positions()

        for position in positions:
            await self._manage_position(position)

    async def _manage_position(self, position: PositionSchema):
        current_price = await self.state.get_current_price(position.symbol)
        current_atr = await self.atr.get_current(position.symbol)
        config = position.management_config

        await self._check_break_even(position, current_price, current_atr, config)
        await self._check_trailing_stop(position, current_price, current_atr, config)
        await self._check_partial_exit(position, current_price, config)
        await self._check_time_exit(position, config)

    async def _check_break_even(
        self,
        position: PositionSchema,
        current_price: float,
        current_atr: float,
        config: PositionManagementConfig
    ):
        if position.stop_loss_moved_to_breakeven:
            return

        trigger_distance = current_atr * config.break_even_trigger_atr

        if position.side == "LONG":
            profit = current_price - position.entry_price
            if profit >= trigger_distance:
                await self._move_stop_to_breakeven(position)
        else:
            profit = position.entry_price - current_price
            if profit >= trigger_distance:
                await self._move_stop_to_breakeven(position)

    async def _check_trailing_stop(
        self,
        position: PositionSchema,
        current_price: float,
        current_atr: float,
        config: PositionManagementConfig
    ):
        trailing_distance = current_atr * config.trailing_stop_atr_multiplier

        if position.side == "LONG":
            new_stop = current_price - trailing_distance
            if new_stop > position.current_stop_loss:
                await self._update_stop_loss(position, new_stop)
        else:
            new_stop = current_price + trailing_distance
            if new_stop < position.current_stop_loss:
                await self._update_stop_loss(position, new_stop)

    async def _check_partial_exit(
        self,
        position: PositionSchema,
        current_price: float,
        config: PositionManagementConfig
    ):
        if position.partial_exit_done:
            return

        if config.partial_exit_at_percent <= 0:
            return

        target_distance = abs(position.take_profit - position.entry_price)
        trigger_distance = target_distance * config.partial_exit_at_percent

        if position.side == "LONG":
            if current_price >= position.entry_price + trigger_distance:
                await self._execute_partial_exit(position, config.partial_exit_size)
        else:
            if current_price <= position.entry_price - trigger_distance:
                await self._execute_partial_exit(position, config.partial_exit_size)

    async def _check_time_exit(
        self,
        position: PositionSchema,
        config: PositionManagementConfig
    ):
        if config.max_hold_time_hours <= 0:
            return

        age_hours = (time.time() * 1000 - position.opened_at_ms) / (1000 * 60 * 60)

        if age_hours >= config.max_hold_time_hours:
            pnl_percent = self._calculate_pnl_percent(position)

            if abs(pnl_percent) < 0.5:
                logger.info(
                    "Position %s stale after %d hours with %.2f%% PnL, closing",
                    position.id, age_hours, pnl_percent
                )
                await self.executor.close_position(position)

    async def _move_stop_to_breakeven(self, position: PositionSchema):
        new_stop = position.entry_price * 1.001

        await self._update_stop_loss(position, new_stop)
        position.stop_loss_moved_to_breakeven = True
        await self.state.update_position(position)

        logger.info("Moved SL to break-even for position %s", position.id)

    async def _execute_partial_exit(
        self,
        position: PositionSchema,
        exit_size_percent: float
    ):
        exit_qty = position.quantity * exit_size_percent

        await self.executor.partial_close(position, exit_qty)

        position.quantity -= exit_qty
        position.partial_exit_done = True
        await self.state.update_position(position)

        logger.info(
            "Partial exit %.2f%% for position %s",
            exit_size_percent * 100, position.id
        )
```

### 6. Order Executor

Translates validated decisions into exchange orders with immediate SL/TP.

```python
class OrderExecutor:
    def __init__(
        self,
        exchange: BinanceClient,
        state_manager: StateManager,
        event_emitter: EventEmitter
    ):
        self.exchange = exchange
        self.state = state_manager
        self.events = event_emitter

    async def execute(
        self,
        decision: DecisionMessage,
        adjustments: dict[str, Any]
    ) -> ExecutionResult:
        adjusted_qty = decision.quantity * adjustments.get("size_multiplier", 1.0)

        await self.events.emit(OrderCreatedEvent(
            decision_id=decision.decision_id,
            symbol=decision.symbol,
            side=decision.action,
            quantity=adjusted_qty,
            price=decision.entry_price
        ))

        try:
            order_response = await self.exchange.create_order(
                symbol=decision.symbol,
                side=OrderSide.BUY if decision.action == "BUY" else OrderSide.SELL,
                order_type=OrderType.LIMIT,
                quantity=Decimal(str(adjusted_qty)),
                price=Decimal(str(decision.entry_price)),
                time_in_force=TimeInForce.GTC
            )

            await self.events.emit(OrderSubmittedEvent(
                decision_id=decision.decision_id,
                order_id=str(order_response.order_id),
                symbol=decision.symbol
            ))

            if order_response.status == OrderStatus.FILLED:
                await self._handle_fill(decision, order_response, adjusted_qty)

            return ExecutionResult(
                success=True,
                order_id=str(order_response.order_id),
                status=order_response.status.value
            )

        except ExchangeError as e:
            await self.events.emit(OrderRejectedEvent(
                decision_id=decision.decision_id,
                symbol=decision.symbol,
                reason=str(e)
            ))
            return ExecutionResult(success=False, error=str(e))

    async def _handle_fill(
        self,
        decision: DecisionMessage,
        order: OrderResponseSchema,
        quantity: float
    ):
        position = PositionSchema(
            id=str(uuid.uuid4()),
            symbol=decision.symbol,
            side="LONG" if decision.action == "BUY" else "SHORT",
            quantity=quantity,
            entry_price=float(order.price),
            stop_loss=decision.stop_loss,
            take_profit=decision.take_profit,
            current_stop_loss=decision.stop_loss,
            management_config=decision.position_management,
            stop_loss_moved_to_breakeven=False,
            partial_exit_done=False,
            opened_at_ms=int(time.time() * 1000)
        )

        await self.state.update_position(position)

        await asyncio.gather(
            self._place_stop_loss(position),
            self._place_take_profit(position)
        )

    async def _place_stop_loss(self, position: PositionSchema):
        side = OrderSide.SELL if position.side == "LONG" else OrderSide.BUY

        await self.exchange.create_order(
            symbol=position.symbol,
            side=side,
            order_type=OrderType.STOP_LOSS_LIMIT,
            quantity=Decimal(str(position.quantity)),
            stop_price=Decimal(str(position.stop_loss)),
            price=Decimal(str(position.stop_loss * 0.999)),
            time_in_force=TimeInForce.GTC
        )

    async def _place_take_profit(self, position: PositionSchema):
        side = OrderSide.SELL if position.side == "LONG" else OrderSide.BUY

        await self.exchange.create_order(
            symbol=position.symbol,
            side=side,
            order_type=OrderType.TAKE_PROFIT_LIMIT,
            quantity=Decimal(str(position.quantity)),
            stop_price=Decimal(str(position.take_profit)),
            price=Decimal(str(position.take_profit)),
            time_in_force=TimeInForce.GTC
        )

    async def partial_close(self, position: PositionSchema, quantity: float):
        side = OrderSide.SELL if position.side == "LONG" else OrderSide.BUY

        await self.exchange.create_order(
            symbol=position.symbol,
            side=side,
            order_type=OrderType.MARKET,
            quantity=Decimal(str(quantity))
        )

        await self._update_sl_tp_quantities(position, position.quantity - quantity)
```

## Event Types

### Trading Events

| Event | Trigger | Data |
|-------|---------|------|
| `OrderCreatedEvent` | Decision received | decision_id, symbol, side, qty, price |
| `OrderSubmittedEvent` | Order sent to exchange | decision_id, order_id, symbol |
| `OrderAcceptedEvent` | Exchange acknowledged | order_id, exchange_order_id |
| `OrderFilledEvent` | Order executed | order_id, filled_qty, avg_price |
| `OrderRejectedEvent` | Exchange/validation rejected | order_id, reason |
| `OrderCancelledEvent` | Order cancelled | order_id, reason |
| `PositionOpenedEvent` | Fill created position | position_id, symbol, entry_price |
| `PositionClosedEvent` | Position fully closed | position_id, exit_price, pnl |
| `StopLossTriggeredEvent` | SL order filled | position_id, exit_price |
| `TakeProfitTriggeredEvent` | TP order filled | position_id, exit_price |
| `StopLossMovedEvent` | Trailing or break-even | position_id, old_sl, new_sl |
| `PartialExitEvent` | Partial profit taken | position_id, exit_qty, exit_price |

### System Events

| Event | Trigger | Data |
|-------|---------|------|
| `WebSocketConnectedEvent` | Stream connected | stream_name, symbol |
| `WebSocketDisconnectedEvent` | Stream lost | stream_name, reason |
| `ReconciliationCompletedEvent` | State synced | discrepancies_count |
| `HealthCheckFailedEvent` | Component unhealthy | component, error |
| `VolatilityRegimeChangedEvent` | Regime shift | symbol, old_regime, new_regime |
| `DrawdownThresholdEvent` | Drawdown limit hit | current_drawdown, threshold |

## Async Loop Structure

### Main Orchestrator

```python
class SpineOrchestrator:
    def __init__(
        self,
        config: SpineConfig,
        redis: Redis,
        exchange: BinanceClient
    ):
        self.config = config
        self.redis = redis
        self.exchange = exchange

        self.volatility_detector = VolatilityRegimeDetector()
        self.state_manager = StateManager(redis, exchange)
        self.risk_validator = DynamicRiskValidator(
            config.risk,
            self.state_manager,
            self.volatility_detector
        )
        self.order_executor = OrderExecutor(exchange, self.state_manager)
        self.position_manager = PositionManager(
            self.state_manager,
            self.order_executor,
            ATRCalculator()
        )
        self.ws_manager = WebSocketManager(exchange, redis, config.symbols)
        self.order_flow_fetcher = OrderFlowFetcher(
            exchange, redis, config.symbols
        )
        self.trigger_engine = TriggerEngine(redis)

    async def start(self):
        await self.state_manager.reconcile_with_exchange()

        await asyncio.gather(
            self._run_data_ingest_loop(),
            self._run_order_flow_loop(),
            self._run_execution_loop(),
            self._run_position_management_loop(),
            self._run_health_check_loop(),
            return_exceptions=True
        )

    async def _run_data_ingest_loop(self):
        await self.ws_manager.start()

    async def _run_order_flow_loop(self):
        await self.order_flow_fetcher.start()

    async def _run_execution_loop(self):
        while True:
            decision_json = await self.redis.brpop(
                "kt:decisions:pending",
                timeout=1
            )

            if decision_json:
                decision = DecisionMessage.model_validate_json(decision_json[1])

                validation = await self.risk_validator.validate(decision)

                if validation.is_valid:
                    await self.order_executor.execute(
                        decision,
                        validation.adjustments
                    )
                else:
                    await self._log_rejected(decision, validation.errors)

    async def _run_position_management_loop(self):
        await self.position_manager.start()

    async def _run_health_check_loop(self):
        while True:
            await asyncio.sleep(30)
            await self._check_component_health()

    async def shutdown(self):
        await self.ws_manager.stop()
        await self.redis.close()
```

## Startup and Recovery

When the system starts (or restarts after a crash), it performs a full state reconciliation to ensure consistency with the exchange.

### Startup Sequence

```
┌─────────────────────────────────────────────────────────────┐
│                    STARTUP SEQUENCE                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. Load Configuration                                      │
│     └─► Read config.yaml, validate schemas                  │
│                                                             │
│  2. Connect to Infrastructure                               │
│     ├─► Redis connection                                    │
│     └─► Database connection (event store)                   │
│                                                             │
│  3. Load Persisted State from Redis                         │
│     ├─► Read kt:state:positions                             │
│     ├─► Read kt:state:orders                                │
│     └─► Read kt:state:account                               │
│                                                             │
│  4. Reconcile with Exchange (CRITICAL)                      │
│     ├─► Fetch account balances from Binance                 │
│     ├─► Fetch open orders from Binance                      │
│     ├─► Compare with local state                            │
│     ├─► Update local state to match exchange                │
│     ├─► Verify SL/TP orders still in place                  │
│     └─► Log any discrepancies                               │
│                                                             │
│  5. Start Async Loops                                       │
│     ├─► WebSocket connections (data ingest)                 │
│     ├─► Order flow fetcher                                  │
│     ├─► Execution loop (order processing)                   │
│     ├─► Position management loop                            │
│     └─► Health check loop                                   │
│                                                             │
│  6. Resume Normal Operation                                 │
│     └─► System ready for new LLM decisions                  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### State Reconciliation Details

```python
class StateManager:
    async def reconcile_with_exchange(self) -> ReconciliationResult:
        logger.info("Starting state reconciliation with exchange")
        discrepancies: list[str] = []

        account_info = await self.exchange.get_account_info()
        open_orders = await self.exchange.get_open_orders()

        for balance in account_info["balances"]:
            asset = balance["asset"]
            exchange_qty = float(balance["free"]) + float(balance["locked"])

            local_position = await self.get_position(f"{asset}USDT")
            local_qty = local_position.quantity if local_position else 0.0

            if abs(exchange_qty - local_qty) > 0.00001:
                discrepancies.append(
                    f"Position mismatch {asset}: local={local_qty}, exchange={exchange_qty}"
                )
                await self._sync_position_from_exchange(asset, exchange_qty)

        local_orders = await self.get_all_open_orders()
        exchange_order_ids = {str(o["orderId"]) for o in open_orders}
        local_order_ids = {o.order_id for o in local_orders}

        for order in open_orders:
            if str(order["orderId"]) not in local_order_ids:
                discrepancies.append(f"Unknown order: {order['orderId']}")
                await self._import_order_from_exchange(order)

        for local_order in local_orders:
            if local_order.order_id not in exchange_order_ids:
                discrepancies.append(f"Stale order: {local_order.order_id}")
                await self._handle_missing_order(local_order)

        for position in await self.get_all_positions():
            await self._verify_protective_orders(position, open_orders)

        logger.info("Reconciliation complete: %d discrepancies", len(discrepancies))
        return ReconciliationResult(success=True, discrepancies=discrepancies)
```

## Configuration Schema

### Trading Configuration

```python
class TradingConfigSchema(BaseModel):
    symbols: list[str]
    interval: str = "15m"
    max_positions: int = 2
```

### Dynamic Risk Configuration ✅ IMPLEMENTED

Located in `spine/risk/config.py`:

```python
class RiskConfigSchema(BaseModel):
    # Core risk settings
    risk_per_trade_percent: Decimal = Decimal("1.0")
    max_positions: int = 2
    min_rr_ratio: Decimal = Decimal("1.5")

    # Drawdown thresholds
    drawdown_pause_percent: Decimal = Decimal("3.0")
    drawdown_close_all_percent: Decimal = Decimal("5.0")

    # ATR limits for stop loss
    min_sl_atr: Decimal = Decimal("0.5")
    max_sl_atr: Decimal = Decimal("3.0")

    # Volatility regime thresholds (ATR Z-score)
    volatility_low_threshold: Decimal = Decimal("-1.0")
    volatility_high_threshold: Decimal = Decimal("1.0")
    volatility_extreme_threshold: Decimal = Decimal("2.0")

    # ATR history for Z-score calculation
    atr_zscore_period: int = 30
```

Size multipliers by volatility regime (defined in `schemas.py`):

| Regime | Z-Score Range | Size Multiplier |
|--------|---------------|-----------------|
| LOW | < -1.0 | 0% |
| NORMAL | -1.0 to 1.0 | 100% |
| HIGH | 1.0 to 2.0 | 50% |
| EXTREME | > 2.0 | 0% |

### Position Management Configuration

```python
class PositionManagementDefaultsSchema(BaseModel):
    trailing_stop_atr_multiplier: float = 1.5
    break_even_trigger_atr: float = 1.0
    partial_exit_at_percent: float = 0.5
    partial_exit_size: float = 0.3
    max_hold_time_hours: int = 24
    scale_in_allowed: bool = False
```

### Infrastructure Configuration

```python
class RedisConfig(BaseModel):
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: str | None = None

class ExchangeConfig(BaseModel):
    api_key: str
    api_secret: str
    testnet: bool = True

class SpineConfig(BaseModel):
    trading: TradingConfigSchema
    risk: RiskConfigSchema
    position_management: PositionManagementDefaultsSchema
    redis: RedisConfig
    exchange: ExchangeConfig

    ws_reconnect_delay_s: float = 1.0
    ws_max_reconnect_delay_s: float = 60.0
    execution_timeout_s: float = 30.0
    order_flow_fetch_interval_s: float = 60.0
    position_check_interval_s: float = 5.0
    health_check_interval_s: float = 30.0

    @property
    def symbols(self) -> list[str]:
        return self.trading.symbols
```

## Metrics and Observability

### Key Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `spine_ws_messages_total` | Counter | WebSocket messages received |
| `spine_ws_reconnects_total` | Counter | Reconnection attempts |
| `spine_orders_submitted_total` | Counter | Orders sent to exchange |
| `spine_orders_filled_total` | Counter | Successfully filled orders |
| `spine_orders_rejected_total` | Counter | Rejected orders |
| `spine_execution_latency_ms` | Histogram | Decision-to-order latency |
| `spine_queue_depth` | Gauge | Pending decisions in queue |
| `spine_positions_open` | Gauge | Current open positions |
| `spine_volatility_regime` | Gauge | Current volatility (0-3) |
| `spine_drawdown_percent` | Gauge | Current drawdown |
| `spine_trailing_stop_updates` | Counter | Trailing stop modifications |
| `spine_partial_exits` | Counter | Partial profit takes |

## Next Steps

For LLM integration with the Spine, see [03_LLM_ARCHITECTURE.md](03_LLM_ARCHITECTURE.md).

For event sourcing implementation, see [EVENT_SOURCING.md](EVENT_SOURCING.md).
