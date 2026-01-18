# KavziTrader Implementation Plan

## Overview

This document outlines the phased implementation roadmap for KavziTrader. The plan builds incrementally, ensuring each phase delivers testable, functional components.

## Current State (Completed)

### Phase 0: Foundation ✅

| Component | Status | Location |
|-----------|--------|----------|
| Project structure | ✅ Done | `kavzi_trader/` |
| Binance REST client | ✅ Done | `api/binance/client.py` |
| WebSocket handlers | ✅ Done | `api/binance/websocket/` |
| Historical data downloaders | ✅ Done | `api/binance/historical/` |
| Common schemas | ✅ Done | `api/common/models.py` |
| CLI framework | ✅ Done | `cli/` |
| Logging utilities | ✅ Done | `commons/logging.py` |
| Time utilities | ✅ Done | `commons/time_utility.py` |
| Configuration system | ✅ Done | `config/` |

### Phase 1: Technical Analysis Foundation ✅

| Component | Status | Location |
|-----------|--------|----------|
| Base converter | ✅ Done | `indicators/base.py` |
| EMA/SMA calculators | ✅ Done | `indicators/trend.py` |
| RSI/MACD calculators | ✅ Done | `indicators/momentum.py` |
| ATR/Bollinger Bands | ✅ Done | `indicators/volatility.py` |
| OBV/Volume ratios | ✅ Done | `indicators/volume.py` |
| Config schemas | ✅ Done | `indicators/config.py` |
| Result schemas | ✅ Done | `indicators/schemas.py` |
| Calculator orchestrator | ✅ Done | `indicators/calculator.py` |
| Unit tests (48 tests) | ✅ Done | `tests/indicators/` |

### Phase 1.5: Order Flow Data Integration ✅

| Component | Status | Location |
|-----------|--------|----------|
| Futures API constants | ✅ Done | `api/binance/constants.py` |
| Futures REST methods | ✅ Done | `api/binance/client.py` |
| Mark price WS handler | ✅ Done | `api/binance/websocket/handlers/mark_price.py` |
| Force order WS handler | ✅ Done | `api/binance/websocket/handlers/force_order.py` |
| Order flow schemas | ✅ Done | `order_flow/schemas.py` |
| Funding Z-score calculator | ✅ Done | `order_flow/funding.py` |
| OI momentum calculator | ✅ Done | `order_flow/open_interest.py` |
| OrderFlowCalculator | ✅ Done | `order_flow/calculator.py` |
| Unit tests (16 tests) | ✅ Done | `tests/order_flow/` |

### Phase 2: State Management Layer ✅

| Component | Status | Location |
|-----------|--------|----------|
| State schemas | ✅ Done | `spine/state/schemas.py` |
| Redis config | ✅ Done | `spine/state/config.py` |
| Async Redis client | ✅ Done | `spine/state/redis_client.py` |
| Position store | ✅ Done | `spine/state/position_store.py` |
| Order store | ✅ Done | `spine/state/order_store.py` |
| Account store | ✅ Done | `spine/state/account_store.py` |
| StateManager | ✅ Done | `spine/state/manager.py` |
| Reconciliation service | ✅ Done | `spine/state/reconciliation.py` |
| Unit tests (60 tests) | ✅ Done | `tests/spine/state/` |

### Phase 3: Dynamic Risk Management ✅

| Component | Status | Location |
|-----------|--------|----------|
| Risk config schema | ✅ Done | `spine/risk/config.py` |
| Volatility regime detector | ✅ Done | `spine/risk/volatility.py` |
| Result schemas | ✅ Done | `spine/risk/schemas.py` |
| ATR-based position sizer | ✅ Done | `spine/risk/position_sizer.py` |
| Exposure limiter | ✅ Done | `spine/risk/exposure.py` |
| DynamicRiskValidator | ✅ Done | `spine/risk/validator.py` |
| Unit tests (33 tests) | ✅ Done | `tests/spine/risk/` |

## Implementation Phases

### Phase 1: Technical Analysis Foundation ✅ COMPLETED

**Duration**: 1-2 weeks

**Goal**: Build the indicator calculation layer that pre-computes all technical analysis for LLM consumption.

#### Implemented Structure

```
kavzi_trader/
├── indicators/
│   ├── __init__.py           # Public exports
│   ├── base.py               # candles_to_dataframe converter
│   ├── config.py             # EMAPeriodsSchema, MACDParamsSchema, etc.
│   ├── trend.py              # calculate_ema(), calculate_sma()
│   ├── momentum.py           # calculate_rsi(), calculate_macd()
│   ├── volatility.py         # calculate_atr(), calculate_bollinger_bands()
│   ├── volume.py             # calculate_obv(), calculate_volume_analysis()
│   ├── schemas.py            # TechnicalIndicatorsSchema, result schemas
│   └── calculator.py         # TechnicalIndicatorCalculator orchestrator
tests/
├── indicators/
│   ├── conftest.py           # Sample candle fixtures
│   ├── test_base.py          # DataFrame conversion tests
│   ├── test_trend.py         # EMA/SMA tests
│   ├── test_momentum.py      # RSI/MACD tests
│   ├── test_volatility.py    # ATR/Bollinger tests
│   ├── test_volume.py        # OBV/Volume tests
│   └── test_calculator.py    # Orchestrator tests
```

#### Indicators Implemented

| Indicator | Function | Description |
|-----------|----------|-------------|
| EMA (20, 50, 200) | `calculate_ema()` | Exponential Moving Average for trend detection |
| SMA (20) | `calculate_sma()` | Simple Moving Average |
| RSI (14) | `calculate_rsi()` | Relative Strength Index for overbought/oversold |
| MACD (12, 26, 9) | `calculate_macd()` | Momentum with signal line and histogram |
| Bollinger Bands | `calculate_bollinger_bands()` | Volatility bands with %B and width |
| ATR (14) | `calculate_atr()` | Average True Range for volatility |
| OBV | `calculate_obv()` | On-Balance Volume for pressure |
| Volume Ratios | `calculate_volume_analysis()` | Current vs average volume |

#### Success Criteria

- [x] All indicators calculate correctly against known test data (48 tests passing)
- [x] Indicators integrate with existing CandlestickSchema data
- [x] TechnicalIndicatorsSchema fully populated from raw candles
- [x] Educational docstrings for non-traders
- [x] Configurable via Pydantic schemas (no bare tuples)

---

### Phase 1.5: Order Flow Data Integration ✅ COMPLETED

**Duration**: 1 week

**Goal**: Add order flow data fetching and processing for trading edge (using Futures data as signals for Spot trading).

#### Implemented Structure

```
kavzi_trader/
├── api/
│   └── binance/
│       ├── constants.py              # Added Futures API URLs
│       ├── client.py                 # Added Futures REST methods
│       ├── schemas/
│       │   └── data_dicts.py         # Added MarkPriceData, ForceOrderData
│       └── websocket/
│           ├── client.py             # Added subscribe_mark_price_stream(), etc.
│           └── handlers/
│               ├── mark_price.py     # Funding rate via WebSocket
│               └── force_order.py    # Liquidation events via WebSocket
├── order_flow/
│   ├── __init__.py                   # Public exports
│   ├── schemas.py                    # OrderFlowSchema, FundingRateSchema, etc.
│   ├── funding.py                    # calculate_funding_zscore()
│   ├── open_interest.py              # calculate_oi_momentum()
│   └── calculator.py                 # OrderFlowCalculator orchestrator
tests/
├── order_flow/
│   ├── conftest.py                   # Sample fixtures
│   ├── test_funding.py               # Funding Z-score tests
│   ├── test_open_interest.py         # OI momentum tests
│   └── test_calculator.py            # Orchestrator tests
```

#### Order Flow Data Implemented

| Data | Source | Method |
|------|--------|--------|
| Funding Rate | REST/WS | `get_funding_rate()`, `subscribe_mark_price_stream()` |
| Open Interest | REST | `get_open_interest()`, `get_open_interest_history()` |
| Long/Short Ratio | REST | `get_long_short_ratio()` |
| Liquidations | WS | `subscribe_force_order_stream()` |

#### Analysis Functions

| Function | Description |
|----------|-------------|
| `calculate_funding_zscore()` | Z-score from historical funding rates (30-period window) |
| `calculate_oi_momentum()` | OI % change at 1h and 24h windows |
| `OrderFlowCalculator.calculate()` | Orchestrates all order flow analysis |

#### Key Schema: OrderFlowSchema

Computed fields for trading signals:

- `is_crowded_long`: funding_zscore > 2.0
- `is_crowded_short`: funding_zscore < -2.0
- `squeeze_alert`: OI change > 5% with price change < 0.5%

#### Success Criteria

- [x] Funding rate fetched and Z-score calculated correctly
- [x] OI changes tracked at 1h and 24h windows
- [x] OrderFlowSchema fully populated from combined data sources
- [x] Unit tests cover all calculators (16 tests passing)
- [x] WebSocket handlers for real-time funding rate updates

---

### Phase 2: State Management Layer ✅ COMPLETED

**Duration**: 1-2 weeks

**Goal**: Implement persistent state management for positions, orders, and account state.

#### Implemented Structure

```
kavzi_trader/
├── spine/
│   ├── __init__.py
│   └── state/
│       ├── __init__.py           # Public exports
│       ├── schemas.py            # PositionSchema, OpenOrderSchema, AccountStateSchema
│       ├── config.py             # RedisConfigSchema
│       ├── redis_client.py       # Async Redis wrapper (redis.asyncio)
│       ├── position_store.py     # Position CRUD operations
│       ├── order_store.py        # Open order CRUD operations
│       ├── account_store.py      # Account balance with drawdown tracking
│       ├── manager.py            # StateManager orchestrator
│       └── reconciliation.py     # Exchange state sync service
tests/
├── spine/
│   └── state/
│       ├── conftest.py           # Shared fixtures
│       ├── test_schemas.py       # Schema validation tests
│       ├── test_position_store.py
│       ├── test_order_store.py
│       ├── test_account_store.py
│       ├── test_manager.py
│       └── test_reconciliation.py
```

#### Key Components

| Component | Description |
|-----------|-------------|
| `PositionSchema` | Tracks open positions with management config (trailing stops, partial exits) |
| `OpenOrderSchema` | Tracks pending orders on exchange with position linking |
| `AccountStateSchema` | Tracks balances with peak/drawdown calculation |
| `RedisStateClient` | Async wrapper for redis.asyncio with typed operations |
| `StateManager` | Unified interface orchestrating all stores |
| `ReconciliationService` | Syncs local state with exchange on startup |

#### Redis Key Patterns

| Key | Purpose |
|-----|---------|
| `kt:state:positions:{id}` | Position data |
| `kt:state:orders:{id}` | Open order data |
| `kt:state:account` | Account state |

#### Success Criteria

- [x] State persists across restarts (Redis persistence)
- [x] State reconciles with Binance on startup
- [x] Position tracking matches exchange state
- [x] Unit tests cover all CRUD operations (60 tests passing)

---

### Phase 3: Dynamic Risk Management ✅ COMPLETED

**Duration**: 1.5 weeks

**Goal**: Build volatility-aware risk validation layer with dynamic position sizing.

#### Implemented Structure

```
kavzi_trader/
├── spine/
│   └── risk/
│       ├── __init__.py           # Public exports
│       ├── config.py             # RiskConfigSchema
│       ├── schemas.py            # VolatilityRegime enum, result schemas
│       ├── volatility.py         # VolatilityRegimeDetector
│       ├── position_sizer.py     # ATR-based PositionSizer
│       ├── exposure.py           # ExposureLimiter
│       └── validator.py          # DynamicRiskValidator orchestrator
tests/
├── spine/
│   └── risk/
│       ├── conftest.py           # Shared fixtures
│       ├── test_volatility.py    # Volatility regime tests
│       ├── test_position_sizer.py
│       ├── test_exposure.py
│       └── test_validator.py     # Validator orchestrator tests
```

#### Key Components

| Component | Description |
|-----------|-------------|
| `RiskConfigSchema` | Configurable thresholds for risk %, drawdown limits, ATR limits |
| `VolatilityRegimeDetector` | Classifies LOW/NORMAL/HIGH/EXTREME from ATR Z-score |
| `PositionSizer` | Calculates position size based on ATR and regime multipliers |
| `ExposureLimiter` | Enforces max positions (2) and prevents duplicate symbols |
| `DynamicRiskValidator` | Orchestrates all checks: drawdown, exposure, volatility, SL/TP |

#### Risk Adjustment Rules

| Condition | Position Size Adjustment |
|-----------|-------------------------|
| Volatility = LOW | 0% (blocked - no movement) |
| Volatility = NORMAL | 100% of calculated size |
| Volatility = HIGH | 50% of calculated size |
| Volatility = EXTREME | 0% (blocked - too risky) |
| Drawdown > 3% | No new positions |
| Drawdown > 5% | Close all positions |

#### Success Criteria

- [x] Position sizing adjusts based on ATR (33 tests passing)
- [x] Volatility regime correctly identified via Z-score
- [x] Drawdown tracking prevents overtrading
- [x] Exposure limits enforced (max 2 positions, no duplicates)

---

### Phase 3.5: Pre-Trade Filters (Trading Plan) ✅ COMPLETED

**Duration**: 1 week

**Goal**: Implement algorithmic pre-filters from the Trading Plan to reduce LLM costs and enforce discipline.

#### Tasks

| Task | Priority | Effort | Dependencies |
|------|----------|--------|--------------|
| Implement liquidity awareness | High | 0.5 days | None |
| Implement news event calendar | Medium | 1 day | External API |
| Implement funding rate filter | High | 0.5 days | Order flow |
| Implement correlation checker | Medium | 0.5 days | State manager |
| Implement minimum movement filter | Medium | 0.5 days | ATR |
| Implement algorithm confluence calculator | High | 1 day | All indicators |
| Create PreTradeFilterChain | High | 0.5 days | All filters |
| Write unit tests | High | 1 day | All |

#### Deliverables

```
kavzi_trader/
├── spine/
│   └── filters/
│       ├── __init__.py
│       ├── config.py            # FilterConfigSchema
│       ├── liquidity.py         # Liquidity/time awareness
│       ├── liquidity_period.py  # LiquidityPeriod enum
│       ├── liquidity_session_schema.py
│       ├── news.py              # News event filter
│       ├── news_event_schema.py
│       ├── funding.py           # Funding rate filter
│       ├── correlation.py       # Correlation filter
│       ├── movement.py          # Minimum movement filter
│       ├── confluence.py        # Algorithm confluence calc
│       ├── schemas.py           # Filter result schemas
│       └── chain.py             # PreTradeFilterChain
tests/
├── spine/
│   └── filters/
│       ├── conftest.py
│       ├── test_chain.py
│       ├── test_confluence.py
│       ├── test_correlation.py
│       ├── test_funding.py
│       ├── test_liquidity.py
│       ├── test_movement.py
│       └── test_news.py
```

#### Filter Priority Order

| Order | Filter | Action |
|-------|--------|--------|
| 1 | Volatility | Skip if EXTREME or LOW regime |
| 2 | News | Skip during major event window |
| 3 | Funding | Block trades against extreme funding |
| 4 | Movement | Skip doji/no-body candle |
| 5 | Position | Skip if max positions reached |
| 6 | Liquidity | Adjust size (weekend/off-hours) |
| 7 | Correlation | Reduce size for correlated exposure |

#### Success Criteria

- [x] 80%+ of candles filtered before LLM
- [x] Session filter blocks weekend/off-hours
- [x] Funding filter blocks crowded trades
- [x] Algorithm confluence score calculated correctly

---

### Phase 4: LLM Integration Core (Tiered Agents) ✅ COMPLETED

**Duration**: 2-3 weeks

**Goal**: Implement the tiered PydanticAI agents (Scout → Analyst → Trader) with confidence calibration.

**Status**: Core implementation complete; performance validation pending.

#### Tasks

| Task | Priority | Effort | Dependencies |
|------|----------|--------|--------------|
| Add pydantic-ai dependency | High | 0.5 days | None |
| Design ScoutDecisionSchema | High | 0.5 days | None |
| Design AnalystDecisionSchema | High | 0.5 days | None |
| Design TradeDecisionSchema with validators | High | 1 day | None |
| Design PositionManagementSchema | High | 0.5 days | None |
| Implement Scout Agent (Haiku) | High | 1 day | Schemas |
| Implement Analyst Agent (Sonnet) | High | 1 day | Schemas |
| Implement Trader Agent (Opus) | High | 1.5 days | Schemas |
| Implement TradingDependencies with order flow | High | 1 day | Order flow |
| Create ContextBuilder for each tier | High | 2 days | All data sources |
| Write system prompts for each agent | High | 1 day | None |
| Implement AgentRouter (triage logic) | High | 1 day | All agents |
| Implement ConfidenceCalibrator | High | 1.5 days | Agent |
| Implement self-correction loop | High | 0.5 days | Agent |
| Add read-only tools | Medium | 1 day | Agent |
| Write integration tests | High | 2 days | All |

#### Deliverables

```
kavzi_trader/
├── brain/
│   ├── __init__.py
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── scout.py          # Scout agent (Haiku)
│   │   ├── analyst.py        # Analyst agent (Sonnet)
│   │   ├── trader.py         # Trader agent (Opus)
│   │   ├── router.py         # AgentRouter
│   │   └── tools.py          # Read-only tools
│   ├── context/
│   │   ├── __init__.py
│   │   ├── builder.py        # ContextBuilder
│   │   ├── formatters.py     # JSON formatters
│   │   └── market_snapshot.py
│   ├── calibration/
│   │   ├── __init__.py
│   │   ├── calibrator.py     # ConfidenceCalibrator
│   │   └── history.py        # Confidence history store
│   ├── prompts/
│   │   ├── __init__.py
│   │   ├── loader.py         # Jinja2 loader
│   │   └── templates/        # Prompt templates
│   └── schemas/
│       ├── __init__.py
│       ├── scout.py          # ScoutDecisionSchema
│       ├── analyst.py        # AnalystDecisionSchema
│       ├── decision.py       # TradeDecisionSchema
│       ├── position_mgmt.py  # PositionManagementSchema
│       └── dependencies.py   # TradingDependencies
```

#### Success Criteria

- [ ] Scout filters 90%+ of candles correctly
- [ ] Agent produces valid TradeDecisionSchema
- [ ] Validation firewall catches invalid outputs
- [ ] Confidence calibration tracks accuracy
- [ ] Cost per decision reduced by tiered approach
- [ ] Context includes order flow data

---

### Phase 5: Active Position Management ✅ COMPLETED

**Duration**: 1.5 weeks

**Goal**: Implement dynamic position management with trailing stops, partial exits, and scaling.

#### Tasks

| Task | Priority | Effort | Dependencies |
|------|----------|--------|--------------|
| Design PositionManagementConfig | High | 0.5 days | None |
| Implement trailing stop logic | High | 1.5 days | ATR indicator |
| Implement break-even mover | High | 0.5 days | Position state |
| Implement partial exit logic | High | 1 day | Order executor |
| Implement time-based exit check | Medium | 0.5 days | Position state |
| Implement scale-in logic | Medium | 1 day | Risk validator |
| Create PositionManager class | High | 1 day | All above |
| Write unit tests | High | 1 day | All |

#### Deliverables

```
kavzi_trader/
├── spine/
│   └── position/
│       ├── __init__.py
│       ├── schemas.py
│       ├── position_action_type.py
│       ├── position_action_schema.py
│       ├── break_even.py      # Break-even mover
│       ├── trailing.py        # Trailing stop logic
│       ├── partial_exit.py    # Partial profit taking
│       ├── scaling.py         # Scale-in logic
│       ├── time_exit.py       # Time-based exits
│       └── manager.py         # PositionManager orchestrator
```

#### Position Management Rules

| Feature | Trigger | Action |
|---------|---------|--------|
| Break-even | Price moves 1 ATR profit | Move SL to entry |
| Trailing Stop | Price moves 2 ATR profit | Trail at 1.5 ATR |
| Partial Exit | Price at 50% to TP | Close 30% of position |
| Time Exit | No progress in 24h | Reassess or close |
| Scale In | Retraces to better level | Add up to 1.5x max |

#### Success Criteria

- [x] Trailing stops update correctly on price movement
- [x] Break-even triggers at configured ATR distance
- [x] Partial exits execute at target levels
- [x] Time exits trigger for stale positions
- [x] Scale-in respects risk limits

---

### Phase 6: Execution Engine

**Duration**: 1-2 weeks

**Goal**: Build the order execution layer that translates decisions into Binance orders.

#### Tasks

| Task | Priority | Effort | Dependencies |
|------|----------|--------|--------------|
| Implement position size translator | High | 1 day | Risk module |
| Create ExecutionEngine class | High | 2 days | State, Risk |
| Implement limit order placement | High | 1 day | Binance client |
| Implement immediate SL/TP on fill | High | 1 day | Order placement |
| Implement OCO management | High | 1.5 days | Order placement |
| Add order monitoring | High | 1 day | WebSocket |
| Implement adaptive staleness check | High | 0.5 days | Volatility |
| Implement execution logging | Medium | 0.5 days | All |
| Write integration tests | High | 1 day | All |

#### Deliverables

```
kavzi_trader/
├── spine/
│   └── execution/
│       ├── __init__.py
│       ├── engine.py         # ExecutionEngine
│       ├── translator.py     # Decision to Order translator
│       ├── staleness.py      # Adaptive staleness checker
│       └── monitor.py        # Order monitoring
```

#### Success Criteria

- [ ] Decisions correctly translate to limit orders
- [ ] SL/TP placed immediately on entry fill
- [ ] Adaptive staleness rejects stale signals
- [ ] Order cancellation handled correctly
- [ ] Partial fills tracked accurately

---

### Phase 7: Event Sourcing Integration

**Duration**: 1-2 weeks

**Goal**: Implement event store for complete audit trail.

#### Tasks

| Task | Priority | Effort | Dependencies |
|------|----------|--------|--------------|
| Define core event types | High | 1 day | None |
| Implement event store (PostgreSQL) | High | 2 days | None |
| Create event serialization | High | 1 day | Event types |
| Implement projection engine | High | 2 days | Event store |
| Integrate with execution engine | High | 1 day | Execution |
| Add confidence calibration events | High | 0.5 days | Calibrator |
| Write tests | High | 1 day | All |

#### Deliverables

```
kavzi_trader/
├── events/
│   ├── __init__.py
│   ├── types.py              # Event type definitions
│   ├── store.py              # Event store implementation
│   ├── serialization.py      # Event serialization
│   └── projections/
│       ├── __init__.py
│       ├── engine.py         # Projection engine
│       ├── orders.py         # Order state projection
│       ├── positions.py      # Position projection
│       └── confidence.py     # Confidence tracking projection
```

---

### Phase 8: Main Loop Orchestration

**Duration**: 1 week

**Goal**: Implement the async event loop that ties Brain and Spine together.

#### Tasks

| Task | Priority | Effort | Dependencies |
|------|----------|--------|--------------|
| Implement DataIngestLoop (with order flow) | High | 1 day | WebSocket |
| Implement ReasoningLoop (with agent router) | High | 1.5 days | Agent Router |
| Implement ExecutionLoop | High | 1 day | Execution |
| Implement PositionManagementLoop | High | 1 day | Position Manager |
| Create TradingOrchestrator | High | 1.5 days | All loops |
| Add graceful shutdown | Medium | 0.5 days | Orchestrator |
| Write integration tests | High | 1 day | All |

#### Deliverables

```
kavzi_trader/
├── orchestrator/
│   ├── __init__.py
│   ├── loops/
│   │   ├── __init__.py
│   │   ├── ingest.py         # DataIngestLoop
│   │   ├── order_flow.py     # OrderFlowLoop
│   │   ├── reasoning.py      # ReasoningLoop
│   │   ├── execution.py      # ExecutionLoop
│   │   └── position.py       # PositionManagementLoop
│   └── orchestrator.py       # TradingOrchestrator
```

---

### Phase 9: Paper Trading Mode

**Duration**: 1 week

**Goal**: Implement simulated trading for safe testing.

#### Tasks

| Task | Priority | Effort | Dependencies |
|------|----------|--------|--------------|
| Create PaperTradingEngine | High | 2 days | Execution |
| Implement simulated order matching | High | 1 day | Market data |
| Add paper trading account state | High | 1 day | State |
| Integrate with orchestrator | High | 1 day | Orchestrator |
| Write tests | High | 1 day | All |

---

### Phase 10: CLI Commands & Operations

**Duration**: 1 week

**Goal**: Build operator-facing CLI commands for running the system.

#### Tasks

| Task | Priority | Effort | Dependencies |
|------|----------|--------|--------------|
| Add `trade start` command | High | 1 day | Orchestrator |
| Add `trade stop` command | High | 0.5 days | Orchestrator |
| Add `trade status` command | High | 0.5 days | State |
| Add `trade positions` command | High | 0.5 days | State |
| Add `trade history` command | Medium | 0.5 days | Events |
| Add `model test` command | Medium | 0.5 days | Agent |
| Add `model calibration` command | Medium | 0.5 days | Calibrator |
| Write CLI tests | High | 1 day | All |

---

### Phase 11: Monitoring & Observability

**Duration**: 1 week

**Goal**: Add production monitoring capabilities.

#### Tasks

| Task | Priority | Effort | Dependencies |
|------|----------|--------|--------------|
| Add structured logging | High | 1 day | All modules |
| Implement health checks | High | 0.5 days | All loops |
| Add LLM decision logging | High | 1 day | Agent |
| Add confidence calibration metrics | High | 0.5 days | Calibrator |
| Create performance metrics | Medium | 1 day | Execution |
| Add alerting hooks | Medium | 0.5 days | Events |
| Add cost tracking dashboard data | Medium | 0.5 days | Agent |

---

## Timeline Summary

| Phase | Duration | Cumulative |
|-------|----------|------------|
| Phase 1: Technical Analysis | 2 weeks | 2 weeks |
| Phase 1.5: Order Flow | 1 week | 3 weeks |
| Phase 2: State Management | 2 weeks | 5 weeks |
| Phase 3: Dynamic Risk Management | 1.5 weeks | 6.5 weeks |
| Phase 3.5: Pre-Trade Filters | 1 week | 7.5 weeks |
| Phase 4: LLM Integration (Tiered) | 3 weeks | 10.5 weeks |
| Phase 5: Position Management | 1.5 weeks | 12 weeks |
| Phase 6: Execution Engine | 2 weeks | 14 weeks |
| Phase 7: Event Sourcing | 2 weeks | 16 weeks |
| Phase 8: Main Loop | 1 week | 17 weeks |
| Phase 9: Paper Trading | 1 week | 18 weeks |
| Phase 10: CLI Commands | 1 week | 19 weeks |
| Phase 11: Monitoring | 1 week | 20 weeks |

**Total Estimated Duration**: 20 weeks (~5 months)

## Dependencies to Add

```toml
# pyproject.toml additions

[project]
dependencies = [
    # Existing dependencies...

    # LLM Integration
    "pydantic-ai>=0.1.0",
    "anthropic>=0.40.0",
    "jinja2>=3.1.0",           # Prompt templates

    # Technical Analysis
    "pandas-ta>=0.3.14b",

    # Database
    "asyncpg>=0.30.0",
    "sqlalchemy>=2.0.0",
]
```

## Risk Mitigation

### Technical Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| LLM hallucination | High | Multi-layer validation + confidence calibration |
| API rate limits | Medium | Token bucket rate limiter |
| Network failures | Medium | Auto-reconnect with exponential backoff |
| State corruption | High | Event sourcing + reconciliation |
| LLM cost overrun | Medium | Tiered agent architecture |
| False confidence | High | Statistical confidence calibration |

### Operational Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Runaway orders | Critical | No direct execution tools for LLM |
| Capital loss | Critical | Strict position limits, dynamic sizing |
| Stale signals | High | Adaptive staleness based on volatility |
| Position mismanagement | High | Active trailing, partial exits |
| API key exposure | Critical | Environment variables, no hardcoding |

## Success Metrics

### Phase Completion Criteria

Each phase must meet:

- [ ] All unit tests passing (>90% coverage)
- [ ] Integration tests with mocked exchange
- [ ] Documentation updated
- [ ] Code review completed

### System Readiness Criteria (Pre-Live)

- [ ] 2 weeks successful paper trading
- [ ] Minimum 100 paper trades for statistical significance
- [ ] Positive expectancy demonstrated
- [ ] Drawdown within expected limits
- [ ] Confidence calibration stable (50+ samples per bucket)
- [ ] Event store captures all operations
- [ ] Recovery tested (crash simulation)
- [ ] Cost per decision within budget

## Next Steps

1. Begin Phase 1: Technical Analysis Foundation
2. Set up development environment with pydantic-ai
3. Create feature branches for each phase
4. Establish code review process

## Related Documentation

| Document | Purpose |
|----------|---------|
| [02_ARCHITECTURE.md](02_ARCHITECTURE.md) | System design and Brain-Spine paradigm |
| [03_LLM_ARCHITECTURE.md](03_LLM_ARCHITECTURE.md) | LLM integration with tiered agents |
| [06_SPINE_IMPLEMENTATION.md](06_SPINE_IMPLEMENTATION.md) | Execution layer implementation details |
| [07_TRADING_PLAN.md](07_TRADING_PLAN.md) | Trading methodology and rules |
| [EVENT_SOURCING.md](EVENT_SOURCING.md) | Event store and audit trail |
