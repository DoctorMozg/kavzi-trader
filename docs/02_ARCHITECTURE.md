# KavziTrader System Architecture

## Overview

KavziTrader implements a **Brain-Spine Architecture** that decouples cognitive reasoning (LLM) from deterministic execution (trading engine). This design enables high-latency AI decision-making without compromising real-time market responsiveness.

## Trading Edge Definition

### Where Does the Edge Come From?

KavziTrader's edge derives from **multi-dimensional context synthesis**:

| Edge Source | Description | Why Humans/Algos Miss It |
|-------------|-------------|--------------------------|
| Order Flow + Price Action | Combining liquidation levels, funding rates with chart patterns | Algos see one; humans struggle to process both real-time |
| Volatility-Adjusted Entries | ATR-scaled position sizing and stop placement | Fixed-rule systems ignore market conditions |
| Confluence Detection | Multiple timeframe and indicator alignment | Requires qualitative judgment at scale |
| Regime-Aware Decisions | Different strategies for trending vs ranging | Most systems use static rules |

### Edge Validation Requirements

Before any strategy goes live:

1. **Statistical Significance**: Minimum 100 trades in paper trading
2. **Win Rate + R:R**: Must achieve positive expectancy (Win% × Avg Win > Loss% × Avg Loss)
3. **Drawdown Testing**: Survive simulated 20% drawdown scenarios
4. **Regime Coverage**: Tested across trending, ranging, and volatile periods

## Core Paradigm: Brain and Spine

### The Spine (System 1) - Deterministic Layer

The Spine handles all real-time, latency-sensitive operations:

- **WebSocket Data Ingestion**: Continuous market data streams
- **Order Execution Engine**: Translates decisions into API calls
- **Dynamic Risk Validator**: Volatility-adjusted position limits
- **Position Manager**: Active management with trailing stops, scaling
- **State Manager**: Maintains positions, orders, and account state
- **Heartbeat Manager**: Connection health monitoring

The Spine operates on reflexes - it never blocks, never waits for AI decisions.

### The Brain (System 2) - Probabilistic Layer

The Brain handles complex reasoning and decision-making:

- **Market Analysis Agent**: Evaluates market conditions using LLM
- **Strategy Generator**: Produces trading signals with calibrated confidence
- **Context Builder**: Prepares multi-source market state for LLM
- **Validation Firewall**: Ensures AI outputs are mathematically valid
- **Confidence Calibrator**: Statistical validation of LLM confidence scores

The Brain wakes on triggers (candle close, signal threshold) and operates asynchronously.

## Data Sources Architecture

### Primary Data (Real-Time)

| Data Type | Source | Purpose |
|-----------|--------|---------|
| OHLCV Candles | Binance WebSocket | Price action, patterns |
| Order Book Depth | Binance WebSocket | Liquidity, support/resistance |
| Recent Trades | Binance WebSocket | Volume, aggressor detection |
| User Data | Binance WebSocket | Position updates, fills |

### Order Flow Data (Critical for Edge)

| Data Type | Source | Purpose |
|-----------|--------|---------|
| Funding Rate | Binance Futures API | Market sentiment, crowded trades |
| Open Interest | Binance Futures API | Position buildup, squeeze risk |
| Liquidation Levels | Calculated from OI | Key price magnets |
| Long/Short Ratio | Binance API | Retail positioning |

### Derived Indicators

| Category | Indicators | Purpose |
|----------|------------|---------|
| Trend | EMA (20, 50, 200), SMA | Direction, dynamic S/R |
| Momentum | RSI (14), MACD, Stochastic | Entry timing, divergences |
| Volatility | ATR (14), Bollinger Bands | Position sizing, stop placement |
| Volume | OBV, Volume SMA Ratio | Confirmation, breakout validity |
| Order Flow | Funding Rate Z-Score, OI Change | Sentiment, crowding |

## Component Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         KavziTrader                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                    THE BRAIN (LLM Layer)                  │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐   │  │
│  │  │   Trading   │  │   Context   │  │   Validation    │   │  │
│  │  │    Agent    │  │   Builder   │  │    Firewall     │   │  │
│  │  └──────┬──────┘  └──────┬──────┘  └────────┬────────┘   │  │
│  │         │                │                  │             │  │
│  │  ┌──────┴──────┐  ┌──────┴──────┐  ┌────────┴────────┐   │  │
│  │  │ Confidence  │  │  Order Flow │  │   Cost-Aware    │   │  │
│  │  │ Calibrator  │  │   Builder   │  │    Routing      │   │  │
│  │  └─────────────┘  └─────────────┘  └─────────────────┘   │  │
│  └─────────┼────────────────┼──────────────────┼────────────┘  │
│            │                │                  │                │
│            ▼                ▼                  ▼                │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                  MESSAGE QUEUES (Redis)                   │  │
│  │     ┌──────────────┐              ┌──────────────┐       │  │
│  │     │ MarketData   │              │  Execution   │       │  │
│  │     │    Queue     │              │    Queue     │       │  │
│  │     └──────────────┘              └──────────────┘       │  │
│  └──────────────────────────────────────────────────────────┘  │
│            │                                    │               │
│            ▼                                    ▼               │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                  THE SPINE (Execution Layer)              │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐   │  │
│  │  │  WebSocket  │  │    Order    │  │    Dynamic      │   │  │
│  │  │   Manager   │  │   Executor  │  │  Risk Engine    │   │  │
│  │  └──────┬──────┘  └──────┬──────┘  └────────┬────────┘   │  │
│  │         │                │                  │             │  │
│  │  ┌──────┴──────┐  ┌──────┴──────┐  ┌────────┴────────┐   │  │
│  │  │  Order Flow │  │  Position   │  │     State       │   │  │
│  │  │    Data     │  │   Manager   │  │    Persister    │   │  │
│  │  └─────────────┘  └─────────────┘  └─────────────────┘   │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
                    ┌──────────────────┐
                    │   Binance API    │
                    │  (REST + WS)     │
                    └──────────────────┘
```

## Asynchronous Event-Driven Model

### Producer-Consumer Pattern

The system uses Python's `asyncio` with three concurrent loops:

#### 1. Data Ingest Loop (Producer)

```
WebSocket → Normalize → Update Local State → Push to MarketDataQueue
         → Order Flow API (periodic) → Enrich State
```

Responsibilities:
- Maintain WebSocket connections with auto-reconnect
- Process klines, depth updates, trade streams
- Fetch order flow data (funding, OI) every 1-5 minutes
- Update local order book mirror
- Handle execution reports for position tracking

#### 2. Reasoning Loop (Consumer)

```
MarketDataQueue → Trigger Check → Snapshot → Agent Router → ExecutionQueue
```

Responsibilities:
- Monitor for trigger conditions (candle close, threshold breach)
- Create immutable market snapshots with order flow
- Route to appropriate agent tier (Scout → Analyst → Trader)
- Run PydanticAI agent with cost awareness
- Validate and queue decisions

#### 3. Execution Loop (Actuator)

```
ExecutionQueue → Dynamic Risk Validation → Order Placement → Position Management
```

Responsibilities:
- Consume trade decisions
- Apply volatility-adjusted risk checks
- Execute via Binance REST API
- Manage dynamic position (trailing stops, partial exits)
- Update position state

## Data Flow

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Binance   │────►│  WebSocket  │────►│   Market    │
│  WebSocket  │     │   Handler   │     │   State     │
└─────────────┘     └─────────────┘     └──────┬──────┘
                                               │
┌─────────────┐     ┌─────────────┐            │
│   Binance   │────►│ Order Flow  │────────────┤
│  REST API   │     │  Fetcher    │            │
└─────────────┘     └─────────────┘            │
                                               ▼
                    ┌─────────────────────────────────────┐
                    │           Trigger Engine            │
                    │  (Candle Close / Signal Threshold)  │
                    └──────────────────┬──────────────────┘
                                       │
                                       ▼
                    ┌─────────────────────────────────────┐
                    │          Context Builder            │
                    │  (OHLCV + Order Flow + Indicators)  │
                    └──────────────────┬──────────────────┘
                                       │
                                       ▼
                    ┌─────────────────────────────────────┐
                    │          Tiered Agent Router        │
                    │   (Scout → Analyst → Trader)        │
                    └──────────────────┬──────────────────┘
                                       │
                                       ▼
                    ┌─────────────────────────────────────┐
                    │        Validation Firewall          │
                    │  (Schema + Risk + Confidence Cal)   │
                    └──────────────────┬──────────────────┘
                                       │
                                       ▼
                    ┌─────────────────────────────────────┐
                    │       Dynamic Risk Engine           │
                    │   (ATR-Adjusted Position Sizing)    │
                    └──────────────────┬──────────────────┘
                                       │
                                       ▼
                    ┌─────────────────────────────────────┐
                    │         Position Manager            │
                    │  (Trailing, Scaling, Partial Exit)  │
                    └──────────────────┬──────────────────┘
                                       │
                                       ▼
                    ┌─────────────────────────────────────┐
                    │           Binance REST              │
                    │        (Limit Orders Only)          │
                    └─────────────────────────────────────┘
```

## Key Design Decisions

### 1. Latency Management

LLM inference takes 2-10 seconds. We mitigate this through:

- **Immutable Snapshots**: LLM analyzes market state at trigger time, immune to drift
- **Limit Orders Only**: Entry orders sit on the book, avoiding slippage
- **Adaptive Staleness**: Dynamic window based on volatility (5s high vol, 30s low vol)
- **Streaming Monitoring**: Track Time-to-First-Token for timeout detection
- **Pre-Computed SL/TP**: Spine immediately places protective orders on fill
- **Tiered Agents**: Quick Scout (500ms) filters before expensive Opus calls

### 2. Strategy Timeframe

The system targets **Swing Trading** and **Intraday Trend Following**:

- 15-minute to 4-hour candle intervals
- Decision horizon measured in minutes/hours, not seconds
- Focus on pattern recognition and regime detection
- Order flow confluence for entry timing

### 3. Safety Architecture

Multiple layers prevent catastrophic failures:

| Layer | Responsibility |
|-------|----------------|
| Pydantic Schema | Type validation, field constraints |
| Model Validator | Cross-field logic (SL < Entry < TP) |
| Confidence Calibrator | Statistical validation of LLM confidence |
| Dynamic Risk Engine | ATR-adjusted position sizing |
| Position Manager | Trailing stops, break-even rules |
| Execution Validator | Price sanity, staleness check |

### 4. Dynamic Risk Management

Risk parameters adjust based on market conditions:

| Condition | Adjustment |
|-----------|------------|
| High ATR (>2x average) | Reduce position size by 50% |
| Elevated funding rate | Avoid adding to direction |
| Low liquidity (weekend) | Widen stops, reduce size |
| Drawdown >3% | Pause new entries |
| Drawdown >5% | Close all positions |

### 5. Position Management

Active position management beyond set-and-forget:

| Feature | Trigger | Action |
|---------|---------|--------|
| Trailing Stop | Price moves 1 ATR in profit | Move stop to break-even |
| Trailing Stop | Price moves 2 ATR in profit | Trail at 1 ATR distance |
| Partial Exit | Price hits 50% to TP | Close 30% of position |
| Time Exit | Position open >24h without progress | Reassess or close |
| Scaling In | Price retraces to better entry | Add up to 1.5x original |

### 6. State Persistence

All state is persisted for crash recovery:

- **Event Store**: Trading events with full audit trail
- **Position Store**: Current positions and open orders
- **Market Cache**: Recent candles and indicator values
- **Confidence History**: LLM decision accuracy tracking

On restart, the system:
1. Loads persisted state from database
2. Reconciles with exchange (fetches open orders)
3. Resumes normal operation

## Cost-Optimized Agent Tiers

| Agent | Model | When Used | Latency | Cost/Decision |
|-------|-------|-----------|---------|---------------|
| Scout | Haiku | Every candle | ~500ms | ~$0.002 |
| Analyst | Sonnet | Scout flags opportunity | ~2s | ~$0.02 |
| Trader | Opus | Analyst confirms setup | ~5s | ~$0.10 |

**Cost Reduction**: 90%+ of candles are filtered by Scout, reducing Opus calls to only high-conviction setups.

## Technology Stack

| Component | Technology |
|-----------|------------|
| Runtime | Python 3.13+ with asyncio |
| LLM Framework | PydanticAI |
| LLM Provider | Anthropic (Haiku, Sonnet, Opus) |
| Exchange API | python-binance |
| Message Queue | Redis |
| Data Validation | Pydantic v2 |
| Database | PostgreSQL (event store) |
| Caching | Redis |

## Module Structure

```
kavzi_trader/
├── api/                    # Exchange connectivity (SPINE) ✅
│   ├── binance/
│   │   ├── client.py       # REST API client (Spot + Futures methods)
│   │   ├── websocket/      # WebSocket handlers (incl. mark_price, force_order)
│   │   └── historical/     # Historical data downloads
│   └── common/             # Shared API interfaces
├── order_flow/             # Order flow analysis ✅
│   ├── schemas.py          # OrderFlowSchema, FundingRateSchema, etc.
│   ├── funding.py          # Funding rate Z-score calculator
│   ├── open_interest.py    # OI momentum calculator
│   └── calculator.py       # OrderFlowCalculator orchestrator
├── brain/                  # LLM integration (BRAIN) (planned)
│   ├── agent/              # Tiered PydanticAI agents
│   ├── context/            # Context window builders
│   ├── prompts/            # System prompts
│   ├── calibration/        # Confidence calibration
│   └── schemas/            # Decision schemas
├── spine/                  # Execution layer (SPINE)
│   ├── execution/          # Order execution engine (planned)
│   ├── risk/               # Dynamic risk validation (planned)
│   ├── position/           # Active position management (planned)
│   └── state/              # State persistence ✅
├── indicators/             # Technical analysis ✅
│   ├── base.py             # DataFrame converter
│   ├── config.py           # Indicator config schemas
│   ├── trend.py            # EMA, SMA calculators
│   ├── momentum.py         # RSI, MACD calculators
│   ├── volatility.py       # ATR, Bollinger Bands
│   ├── volume.py           # OBV, volume ratios
│   ├── schemas.py          # Result schemas
│   └── calculator.py       # Orchestrator
├── strategy/               # Strategy framework (planned)
├── events/                 # Event sourcing (planned)
├── cli/                    # Command-line interface ✅
├── commons/                # Shared utilities ✅
└── config/                 # Configuration ✅
```

## Next Steps

For detailed LLM architecture, see [03_LLM_ARCHITECTURE.md](03_LLM_ARCHITECTURE.md).

For Spine implementation details, see [06_SPINE_IMPLEMENTATION.md](06_SPINE_IMPLEMENTATION.md).

For implementation timeline, see [05_IMPLEMENTATION_PLAN.md](05_IMPLEMENTATION_PLAN.md).
