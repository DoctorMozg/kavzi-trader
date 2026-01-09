# LLM Architecture for KavziTrader

## Overview

KavziTrader uses Large Language Models as a "System 2" reasoning engine for trading decisions. This document details the LLM integration architecture using **PydanticAI** framework with **Anthropic Claude** models.

## Design Philosophy

### Why LLMs for Trading?

Traditional algorithmic trading uses deterministic rules (e.g., "buy when RSI < 30"). LLMs enable:

- **Semantic Reasoning**: Understanding "why" behind market movements
- **Multi-Source Synthesis**: Combining technical indicators, order flow, and sentiment
- **Adaptive Analysis**: Adjusting interpretation based on market regime
- **Natural Language Decisions**: Explainable trade rationale

### The Precision-Velocity Trade-off

We deliberately choose **Precision over Velocity**:

| Aspect | Traditional Algo | LLM-Based |
|--------|------------------|-----------|
| Decision Time | Microseconds | 500ms - 5s (tiered) |
| Strategy Type | Scalping, HFT | Swing, Intraday |
| Signal Source | Pure quantitative | Qualitative-quantitative |
| Adaptability | Static rules | Context-aware |

## Tiered Agent Architecture

To optimize cost and latency, we use a three-tier agent hierarchy:

```
┌─────────────────────────────────────────────────────────┐
│                    Agent Hierarchy                       │
├─────────────────────────────────────────────────────────┤
│                                                          │
│   ┌───────────────────────────────────────────────┐     │
│   │            Scout Agent (Haiku)                 │     │
│   │         Every candle: Quick scan               │     │
│   │         Cost: ~$0.002 | Latency: ~500ms        │     │
│   │         Output: INTERESTING / SKIP             │     │
│   └─────────────────────┬─────────────────────────┘     │
│                         │                                │
│                         ▼ If INTERESTING                 │
│   ┌───────────────────────────────────────────────┐     │
│   │           Analyst Agent (Sonnet)               │     │
│   │         Detailed technical analysis            │     │
│   │         Cost: ~$0.02 | Latency: ~2s            │     │
│   │         Output: SETUP_VALID / NO_SETUP         │     │
│   └─────────────────────┬─────────────────────────┘     │
│                         │                                │
│                         ▼ If SETUP_VALID                 │
│   ┌───────────────────────────────────────────────┐     │
│   │          Trader Agent (Opus)                   │     │
│   │        Final trade decision + sizing           │     │
│   │         Cost: ~$0.10 | Latency: ~5s            │     │
│   │         Output: TradeDecisionSchema            │     │
│   └───────────────────────────────────────────────┘     │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

### Cost Optimization Results

| Scenario | Without Tiers | With Tiers | Savings |
|----------|---------------|------------|---------|
| 100 candles/day | $10/day | ~$0.50/day | 95% |
| 5 pairs × 100 candles | $50/day | ~$2.50/day | 95% |

**Logic**: 90%+ of candles have no setup; Scout filters them cheaply.

## PydanticAI Framework

### Why PydanticAI?

PydanticAI treats LLM interaction as a typed software engineering problem:

- **Schema Enforcement**: Structured outputs, not string parsing
- **Dependency Injection**: Clean separation of concerns
- **Self-Correction**: Automatic retry on validation failure
- **Tool Integration**: LLM can invoke typed functions

### Agent Definitions

```python
from pydantic_ai import Agent
from pydantic_ai.models.anthropic import AnthropicModel

scout_agent = Agent(
    AnthropicModel('claude-3-haiku-20240307'),
    deps_type=ScoutDependencies,
    result_type=ScoutDecisionSchema,
    retries=1
)

analyst_agent = Agent(
    AnthropicModel('claude-3-5-sonnet-20241022'),
    deps_type=AnalystDependencies,
    result_type=AnalystDecisionSchema,
    retries=2
)

trader_agent = Agent(
    AnthropicModel('claude-3-opus-20240229'),
    deps_type=TradingDependencies,
    result_type=TradeDecisionSchema,
    retries=2
)
```

## Data Contracts

### Scout Decision Schema

Quick triage output from Haiku:

```python
class ScoutDecisionSchema(BaseModel):
    verdict: Literal["INTERESTING", "SKIP"]
    reason: Annotated[str, Field(max_length=100)]
    pattern_detected: str | None = None
```

### Analyst Decision Schema

Detailed analysis from Sonnet:

```python
class AnalystDecisionSchema(BaseModel):
    setup_valid: bool
    direction: Literal["LONG", "SHORT", "NEUTRAL"]
    confluence_score: Annotated[int, Field(ge=0, le=10)]
    key_levels: KeyLevelsSchema
    reasoning: str
```

### Trade Decision Schema

The final LLM output is strictly typed:

```python
class TradeDecisionSchema(BaseModel):
    action: Literal["BUY", "SELL", "WAIT", "CLOSE"]
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    reasoning: str
    suggested_entry: float | None = None
    suggested_stop_loss: float | None = None
    suggested_take_profit: float | None = None
    position_management: PositionManagementSchema | None = None

    @model_validator(mode='after')
    def validate_trade_logic(self) -> "TradeDecisionSchema":
        if self.action == "BUY":
            if not all([self.suggested_entry, self.suggested_stop_loss, 
                       self.suggested_take_profit]):
                raise ValueError("BUY requires entry, stop_loss, take_profit")
            if not (self.suggested_stop_loss < self.suggested_entry 
                   < self.suggested_take_profit):
                raise ValueError("BUY: stop_loss < entry < take_profit")
        return self
```

### Position Management Schema

Active position management instructions:

```python
class PositionManagementSchema(BaseModel):
    trailing_stop_atr_multiplier: Annotated[float, Field(ge=0.5, le=3.0)] = 1.5
    break_even_trigger_atr: Annotated[float, Field(ge=0.5, le=2.0)] = 1.0
    partial_exit_at_percent: Annotated[float, Field(ge=0.0, le=1.0)] = 0.5
    partial_exit_size: Annotated[float, Field(ge=0.0, le=0.5)] = 0.3
    max_hold_time_hours: Annotated[int, Field(ge=1, le=168)] = 24
    scale_in_allowed: bool = False
    scale_in_max_multiplier: Annotated[float, Field(ge=1.0, le=2.0)] = 1.5
```

### Trading Dependencies

Context injected into every agent run:

```python
class TradingDependencies(BaseModel):
    symbol: str
    current_price: float
    account_balance: float
    open_positions: list[PositionSchema]
    market_data: MarketDataSchema
    indicators: TechnicalIndicatorsSchema
    order_flow: OrderFlowSchema
    volatility_regime: Literal["LOW", "NORMAL", "HIGH", "EXTREME"]
```

## Order Flow Integration

### Order Flow Schema

Critical data for edge:

```python
class OrderFlowSchema(BaseModel):
    funding_rate: float
    funding_rate_zscore: float
    open_interest: float
    open_interest_change_1h: float
    open_interest_change_24h: float
    long_short_ratio: float
    liquidation_levels_above: list[float]
    liquidation_levels_below: list[float]
    bid_ask_imbalance: float
```

### How Order Flow Informs Decisions

| Signal | Interpretation | Action |
|--------|----------------|--------|
| Funding >0.05% | Longs overcrowded | Avoid new longs |
| OI spike + price flat | Squeeze building | Prepare for breakout |
| Liquidations above | Price magnet | Consider short target |
| Bid imbalance >1.5 | Strong demand | Supports long bias |

## Confidence Calibration

### The Problem with Raw LLM Confidence

LLMs often express arbitrary confidence that doesn't correlate with actual accuracy. An LLM saying "90% confident" means nothing without calibration.

### Calibration Approach

1. **Track Historical Accuracy**: Log every decision with outcome
2. **Bucket by Confidence**: Group decisions by stated confidence
3. **Calculate Actual Win Rate**: Per bucket
4. **Apply Correction Factor**: Adjust future decisions

```python
class ConfidenceCalibrator:
    def __init__(self, history_store: ConfidenceHistoryStore):
        self.history = history_store
    
    def calibrate(self, raw_confidence: float) -> float:
        bucket = self._get_bucket(raw_confidence)
        historical_accuracy = self.history.get_accuracy(bucket)
        
        if historical_accuracy is None:
            return raw_confidence * 0.7
        
        return historical_accuracy
    
    def record_outcome(
        self, 
        decision_id: str, 
        raw_confidence: float, 
        was_correct: bool
    ):
        self.history.record(decision_id, raw_confidence, was_correct)
```

### Confidence Thresholds (Post-Calibration)

| Calibrated Confidence | Action |
|-----------------------|--------|
| < 0.5 | Force WAIT |
| 0.5 - 0.7 | Reduce position size by 50% |
| 0.7 - 0.85 | Normal position size |
| > 0.85 | Allow full position size |

### Bootstrap Period

Until 50+ decisions are recorded, apply conservative defaults:

```python
DEFAULT_CALIBRATION = {
    "raw_0.9+": 0.65,
    "raw_0.8-0.9": 0.55,
    "raw_0.7-0.8": 0.45,
    "raw_below_0.7": 0.35
}
```

## Context Window Engineering

### Data Format Strategy

LLMs parse structured data best in specific formats:

| Data Type | Format | Purpose |
|-----------|--------|---------|
| Current Snapshot | JSON | Precise values for decision |
| Price History | Markdown Table | Visual trend recognition |
| Active Positions | JSON List | Risk context |
| Indicators | JSON | Quantitative signals |
| Order Flow | JSON | Sentiment and positioning |

### Feature Engineering

Pre-compute all indicators locally - never rely on LLM arithmetic:

```python
class TechnicalIndicatorsSchema(BaseModel):
    rsi_14: float
    ema_20: float
    ema_50: float
    ema_200: float
    macd_line: float
    macd_signal: float
    macd_histogram: float
    bollinger_upper: float
    bollinger_lower: float
    bollinger_width: float
    atr_14: float
    volume_sma_ratio: float
    volatility_regime: Literal["LOW", "NORMAL", "HIGH", "EXTREME"]
```

### Context Window Management

Claude models support large contexts, but we use focused windows:

- **Scout**: ~1,000 tokens (last 10 candles, key indicators)
- **Analyst**: ~4,000 tokens (last 50 candles, full indicators, order flow)
- **Trader**: ~6,000 tokens (full context + position state)

## Prompt Engineering

### System vs User Prompt Separation

All prompts are strictly separated:

| Prompt Type | Purpose | Changes Per Request |
|-------------|---------|---------------------|
| **System** | Define agent behavior | Rarely |
| **User** | Provide current context | Every request |

### Jinja2 Template System

Prompts stored as templates in `prompts/templates/`:

```
brain/prompts/templates/
├── system/
│   ├── base/
│   │   ├── role.j2
│   │   ├── risk_rules.j2
│   │   └── output_format.j2
│   └── agents/
│       ├── scout.j2
│       ├── analyst.j2
│       └── trader.j2
└── user/
    ├── context/
    │   ├── market_snapshot.j2
    │   ├── order_flow.j2
    │   └── account_state.j2
    └── requests/
        ├── scout_scan.j2
        ├── analyze_setup.j2
        └── make_decision.j2
```

### Scout System Prompt

```jinja2
<role>
You are a fast market scanner. Your job is to quickly identify if a candle 
shows any interesting pattern worth deeper analysis.
</role>

<task>
Look for: breakouts, divergences, key level tests, unusual volume.
Ignore: sideways chop, no-volume moves, unclear patterns.
</task>

<output>
Respond with INTERESTING or SKIP, and a brief reason (max 20 words).
</output>
```

### Trader System Prompt (with Order Flow)

```jinja2
{% include 'system/base/role.j2' %}

<order_flow_rules>
- If funding_rate_zscore > 2.0, avoid opening positions in that direction
- If OI is spiking without price movement, expect a squeeze
- Use liquidation levels as potential take-profit targets
- Bid/ask imbalance > 1.5 confirms directional bias
</order_flow_rules>

<position_management>
Always specify position management parameters:
- trailing_stop_atr_multiplier: How many ATRs to trail (1.0-2.0 typical)
- break_even_trigger_atr: When to move stop to break-even
- partial_exit_at_percent: Where to take partial profits (0.5 = 50% to TP)
- max_hold_time_hours: Maximum time to hold if no progress
</position_management>

{% include 'system/base/risk_rules.j2' %}
{% include 'system/base/output_format.j2' %}
```

## Validation Firewall

### Layer 1: Schema Validation

Pydantic enforces types and constraints automatically.

### Layer 2: Cross-Field Logic

```python
@model_validator(mode='after')
def validate_risk_reward(self) -> "TradeDecisionSchema":
    if self.action in ["BUY", "SELL"]:
        risk = abs(self.suggested_entry - self.suggested_stop_loss)
        reward = abs(self.suggested_take_profit - self.suggested_entry)
        if reward < (1.5 * risk):
            raise ValueError(f"R:R ratio {reward/risk:.2f} below minimum 1.5")
    return self
```

### Layer 3: Price Sanity

```python
@model_validator(mode='after')
def validate_price_sanity(self) -> "TradeDecisionSchema":
    if self.suggested_entry:
        max_deviation = 0.02  # 2% from current price
        if abs(self.suggested_entry - current_price) / current_price > max_deviation:
            raise ValueError("Entry price deviates >2% from market")
    return self
```

### Layer 4: Confidence Calibration

```python
@model_validator(mode='after')
def apply_confidence_calibration(self) -> "TradeDecisionSchema":
    calibrator = get_confidence_calibrator()
    self.calibrated_confidence = calibrator.calibrate(self.confidence)
    
    if self.calibrated_confidence < 0.5 and self.action in ["BUY", "SELL"]:
        self.action = "WAIT"
        self.reasoning += " [AUTO-OVERRIDE: Low calibrated confidence]"
    return self
```

### Layer 5: Volatility Check

```python
@model_validator(mode='after')
def validate_volatility_conditions(self) -> "TradeDecisionSchema":
    if self.volatility_regime == "EXTREME" and self.action in ["BUY", "SELL"]:
        self.position_size_multiplier = 0.25
        self.reasoning += " [Position reduced 75% due to extreme volatility]"
    return self
```

### Self-Correction Loop

PydanticAI supports automatic retry with error feedback:

```
Agent Output → Validation Error → Error Message to LLM → Regenerate
```

## Latency Management

### Adaptive Staleness Window

Staleness threshold adjusts based on volatility:

```python
def get_staleness_threshold_ms(volatility_regime: str) -> int:
    thresholds = {
        "LOW": 60_000,      # 60 seconds
        "NORMAL": 30_000,   # 30 seconds
        "HIGH": 15_000,     # 15 seconds
        "EXTREME": 5_000    # 5 seconds
    }
    return thresholds.get(volatility_regime, 30_000)
```

### Immediate SL/TP Placement

On fill, the Spine immediately places protective orders:

```python
async def on_entry_filled(self, fill: FillEvent):
    await asyncio.gather(
        self.place_stop_loss(fill),
        self.place_take_profit(fill)
    )
```

### Streaming Timeout Detection

Monitor time-to-first-token for early timeout:

```python
async def run_with_streaming_timeout(agent, prompt, deps, timeout_s=30):
    async with asyncio.timeout(timeout_s):
        async for chunk in agent.run_stream(prompt, deps=deps):
            if chunk.is_first:
                first_token_time = time.time()
            yield chunk
```

## Tool Definitions

### Read-Only Tools (Safe)

```python
@trader_agent.tool
async def get_liquidity_depth(
    ctx: RunContext[TradingDependencies], 
    percent_distance: float
) -> dict[str, float]:
    """Check bid/ask liquidity within % distance from price."""
    return {"bid_liquidity": bid_total, "ask_liquidity": ask_total}

@trader_agent.tool
async def get_recent_liquidations(
    ctx: RunContext[TradingDependencies],
    hours: int = 4
) -> list[LiquidationSchema]:
    """Get recent liquidation events."""
    return liquidations
```

### No Execution Tools

The agent NEVER directly executes orders. It returns a decision object that the Spine processes.

## Error Handling

### Hallucination Mitigation

1. **Grounding**: Provide all data in context - forbid external claims
2. **Order Flow Verification**: Cross-reference claims with actual data
3. **Numerical Grounding**: Pre-compute all indicators, never trust LLM math
4. **Confidence Calibration**: Don't trust raw LLM confidence scores

### Timeout Handling

```python
async def run_with_timeout(agent, prompt, deps, timeout_s=30):
    try:
        async with asyncio.timeout(timeout_s):
            return await agent.run(prompt, deps=deps)
    except asyncio.TimeoutError:
        logger.warning("LLM timeout after %ds", timeout_s)
        return FallbackDecision(action="WAIT", reason="LLM timeout")
```

### Rate Limiting

Token bucket for API calls:

```python
class RateLimiter:
    def __init__(self, requests_per_minute: int = 50):
        self.rate = requests_per_minute
        self.tokens = requests_per_minute
        self.last_update = time.time()
```

## Logging and Audit

Every LLM decision is logged with full context:

```python
class LLMDecisionLog(BaseModel):
    timestamp: datetime
    symbol: str
    agent_tier: Literal["scout", "analyst", "trader"]
    market_snapshot: MarketDataSchema
    order_flow: OrderFlowSchema
    indicators: TechnicalIndicatorsSchema
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int
    raw_confidence: float
    calibrated_confidence: float
    decision: TradeDecisionSchema
    raw_reasoning: str
```

## Implementation Checklist

- [ ] Set up tiered PydanticAI agents (Scout, Analyst, Trader)
- [ ] Define all decision schemas with validators
- [ ] Implement TradingDependencies with order flow
- [ ] Create context builders for each agent tier
- [ ] Write system prompts for each agent
- [ ] Implement confidence calibration system
- [ ] Build order flow data fetcher
- [ ] Implement read-only tools
- [ ] Build validation firewall layers
- [ ] Add adaptive timeout and rate limiting
- [ ] Create decision logging system
- [ ] Test with paper trading

## Next Steps

See [05_IMPLEMENTATION_PLAN.md](05_IMPLEMENTATION_PLAN.md) for phased implementation timeline.
