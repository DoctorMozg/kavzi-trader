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

## Implementation Phases

### Phase 1: Technical Analysis Foundation

**Duration**: 1-2 weeks

**Goal**: Build the indicator calculation layer that pre-computes all technical analysis for LLM consumption.

#### Tasks

| Task | Priority | Effort | Dependencies |
|------|----------|--------|--------------|
| Create `indicators/` module | High | 2 days | None |
| Implement RSI calculator | High | 0.5 days | indicators module |
| Implement EMA calculator (20, 50, 200) | High | 0.5 days | indicators module |
| Implement MACD calculator | High | 0.5 days | EMA |
| Implement Bollinger Bands | Medium | 0.5 days | EMA |
| Implement ATR calculator | Medium | 0.5 days | indicators module |
| Implement Volume analysis | Medium | 0.5 days | indicators module |
| Create TechnicalIndicatorsSchema | High | 0.5 days | All calculators |
| Write unit tests | High | 1 day | All calculators |

#### Deliverables

```
kavzi_trader/
├── indicators/
│   ├── __init__.py
│   ├── base.py              # Base indicator interface
│   ├── trend.py             # EMA, SMA
│   ├── momentum.py          # RSI, MACD, Stochastic
│   ├── volatility.py        # ATR, Bollinger Bands
│   ├── volume.py            # OBV, Volume ratios
│   └── schemas.py           # TechnicalIndicatorsSchema
```

#### Success Criteria

- [ ] All indicators calculate correctly against known test data
- [ ] Indicators integrate with existing kline data
- [ ] TechnicalIndicatorsSchema fully populated from raw candles

---

### Phase 1.5: Order Flow Data Integration

**Duration**: 1 week

**Goal**: Add order flow data fetching and processing for trading edge.

#### Tasks

| Task | Priority | Effort | Dependencies |
|------|----------|--------|--------------|
| Create `order_flow/` module | High | 1 day | None |
| Implement funding rate fetcher | High | 0.5 days | Binance client |
| Implement open interest fetcher | High | 0.5 days | Binance client |
| Implement long/short ratio fetcher | Medium | 0.5 days | Binance client |
| Calculate funding rate Z-score | High | 0.5 days | Funding fetcher |
| Calculate OI change metrics | High | 0.5 days | OI fetcher |
| Estimate liquidation levels | Medium | 1 day | OI data |
| Create OrderFlowSchema | High | 0.5 days | All fetchers |
| Write unit tests | High | 0.5 days | All |

#### Deliverables

```
kavzi_trader/
├── api/
│   └── binance/
│       └── order_flow/
│           ├── __init__.py
│           ├── funding.py       # Funding rate fetcher
│           ├── open_interest.py # OI fetcher
│           ├── ratios.py        # Long/short ratio
│           └── liquidations.py  # Liquidation level estimator
├── indicators/
│   └── order_flow/
│       ├── __init__.py
│       ├── funding_zscore.py    # Funding analysis
│       ├── oi_momentum.py       # OI change analysis
│       └── schemas.py           # OrderFlowSchema
```

#### Success Criteria

- [ ] Funding rate fetched and Z-score calculated correctly
- [ ] OI changes tracked at 1h and 24h windows
- [ ] Liquidation levels estimated from OI distribution
- [ ] OrderFlowSchema integrated into context builder

---

### Phase 2: State Management Layer

**Duration**: 1-2 weeks

**Goal**: Implement persistent state management for positions, orders, and account state.

#### Tasks

| Task | Priority | Effort | Dependencies |
|------|----------|--------|--------------|
| Design state schemas | High | 1 day | None |
| Implement PositionSchema (with management fields) | High | 1 day | Schemas |
| Implement AccountStateSchema | High | 0.5 days | Schemas |
| Create StateManager class | High | 1 day | Schemas |
| Add Redis state persistence | Medium | 1 day | StateManager |
| Implement state reconciliation with exchange | High | 1 day | StateManager |
| Write unit tests | High | 1 day | All |

#### Deliverables

```
kavzi_trader/
├── spine/
│   ├── __init__.py
│   └── state/
│       ├── __init__.py
│       ├── schemas.py        # PositionSchema, AccountStateSchema
│       ├── manager.py        # StateManager
│       └── persistence.py    # Redis persistence
```

#### Success Criteria

- [ ] State persists across restarts
- [ ] State reconciles with Binance on startup
- [ ] Position tracking matches exchange state

---

### Phase 3: Dynamic Risk Management

**Duration**: 1.5 weeks

**Goal**: Build volatility-aware risk validation layer with dynamic position sizing.

#### Tasks

| Task | Priority | Effort | Dependencies |
|------|----------|--------|--------------|
| Define risk configuration schema | High | 0.5 days | None |
| Implement volatility regime detector | High | 1 day | ATR indicator |
| Implement ATR-based position sizer | High | 1 day | Volatility detector |
| Implement dynamic exposure limits | High | 0.5 days | StateManager |
| Implement drawdown tracker | High | 1 day | StateManager |
| Create DynamicRiskValidator class | High | 1 day | All above |
| Write unit tests | High | 1 day | All |

#### Deliverables

```
kavzi_trader/
├── spine/
│   └── risk/
│       ├── __init__.py
│       ├── config.py             # RiskConfigSchema
│       ├── volatility.py         # Volatility regime detector
│       ├── position_sizer.py     # ATR-based sizing
│       ├── validator.py          # DynamicRiskValidator
│       └── tracker.py            # Drawdown, exposure tracking
```

#### Risk Adjustment Rules

| Condition | Position Size Adjustment |
|-----------|-------------------------|
| Volatility = LOW | 100% of calculated size |
| Volatility = NORMAL | 100% of calculated size |
| Volatility = HIGH | 50% of calculated size |
| Volatility = EXTREME | 25% of calculated size |
| Drawdown > 3% | No new positions |
| Drawdown > 5% | Close all positions |

#### Success Criteria

- [ ] Position sizing adjusts based on ATR
- [ ] Volatility regime correctly identified
- [ ] Drawdown tracking prevents overtrading
- [ ] Exposure limits enforced per regime

---

### Phase 3.5: Pre-Trade Filters (Trading Plan)

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
│       ├── liquidity.py         # Liquidity/time awareness
│       ├── news.py              # News event filter
│       ├── funding.py           # Funding rate filter
│       ├── correlation.py       # Correlation filter
│       ├── movement.py          # Minimum movement filter
│       ├── confluence.py        # Algorithm confluence calc
│       └── chain.py             # PreTradeFilterChain
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

- [ ] 80%+ of candles filtered before LLM
- [ ] Session filter blocks weekend/off-hours
- [ ] Funding filter blocks crowded trades
- [ ] Algorithm confluence score calculated correctly

---

### Phase 4: LLM Integration Core (Tiered Agents)

**Duration**: 2-3 weeks

**Goal**: Implement the tiered PydanticAI agents (Scout → Analyst → Trader) with confidence calibration.

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
│   │   ├── order_flow.py     # Order flow context
│   │   └── formatter.py      # Markdown/JSON formatters
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

### Phase 5: Active Position Management

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
│       ├── config.py          # PositionManagementConfig
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

- [ ] Trailing stops update correctly on price movement
- [ ] Break-even triggers at configured ATR distance
- [ ] Partial exits execute at target levels
- [ ] Time exits trigger for stale positions
- [ ] Scale-in respects risk limits

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
