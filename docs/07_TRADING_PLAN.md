# KavziTrader Trading Plan

## Overview

This document defines the trading methodology, valid setups, and decision rules for KavziTrader. It explicitly separates what the LLM handles (qualitative judgment) from what algorithms handle (deterministic rules).

## Responsibility Matrix

### Algorithm-Handled (Spine - Deterministic)

These are fast, rule-based checks that don't need LLM reasoning:

| Component | Logic | Why Algorithm |
|-----------|-------|---------------|
| Session Filter | Only trade during valid sessions | Simple time check |
| Volatility Regime | Classify LOW/NORMAL/HIGH/EXTREME from ATR | Math calculation |
| Drawdown Check | Pause/stop at thresholds | Simple comparison |
| Position Limits | Reject if max positions reached | Counter check |
| Staleness Check | Reject stale signals | Timestamp comparison |
| Funding Rate Filter | Block trades against extreme funding | Threshold check |
| Position Sizing | Calculate size from ATR and risk % | Formula |
| Trailing Stops | Update SL based on price movement | Rule-based |
| Partial Exits | Execute at predefined levels | Threshold trigger |
| Break-Even | Move SL when profit target hit | Simple rule |
| News Filter | Block trading during major events | Calendar lookup |
| Correlation Filter | Reduce exposure on correlated assets | Calculation |

### LLM-Handled (Brain - Qualitative)

These require pattern recognition and contextual judgment:

| Component | Logic | Why LLM |
|-----------|-------|---------|
| Pattern Recognition | Identify chart patterns (H&S, triangles, etc.) | Visual/contextual |
| Confluence Scoring | Assess alignment of multiple signals | Weighted judgment |
| Market Regime | Trending vs ranging interpretation | Context-dependent |
| Entry Timing | Best entry within valid zone | Qualitative |
| Support/Resistance | Identify key price levels | Pattern-based |
| Divergence Detection | RSI/price divergences | Interpretation |
| Setup Quality | Rate setup from A to C | Subjective scoring |
| Trade Narrative | Explain why this trade makes sense | Language |
| Risk Assessment | Assess hidden risks in setup | Contextual |

## Pre-Trade Filters (Algorithm)

These filters run BEFORE the LLM is invoked, saving cost and ensuring discipline.

### 1. Liquidity Awareness (Crypto-Specific)

Crypto is 24/7, but liquidity varies significantly:

```python
LIQUIDITY_PERIODS = {
    "high": {
        "description": "US + Europe overlap",
        "hours_utc": [(13, 21)],
        "size_multiplier": 1.0
    },
    "medium": {
        "description": "Single major session active",
        "hours_utc": [(7, 13), (21, 1)],
        "size_multiplier": 0.8
    },
    "low": {
        "description": "Asia-only or quiet hours",
        "hours_utc": [(1, 7)],
        "size_multiplier": 0.5
    }
}

WEEKEND_RULES = {
    "saturday": {"size_multiplier": 0.5, "reason": "Low liquidity"},
    "sunday_before_20utc": {"size_multiplier": 0.5, "reason": "CME closed"},
    "sunday_after_20utc": {"size_multiplier": 0.8, "reason": "CME opening"}
}
```

**Rule**: Don't block trading, but adjust position size based on expected liquidity.

### 2. Volatility Pre-Filter

| ATR Z-Score | Regime | Action |
|-------------|--------|--------|
| < -1.0 | LOW | Skip (no movement) |
| -1.0 to 1.0 | NORMAL | Proceed to LLM |
| 1.0 to 2.0 | HIGH | Proceed with caution flag |
| > 2.0 | EXTREME | Skip (too risky) |

**Rule**: Only invoke LLM for NORMAL and HIGH regimes. LOW and EXTREME are auto-skipped.

### 3. Funding Rate Filter

| Funding Rate Z-Score | Direction | Action |
|---------------------|-----------|--------|
| > 2.0 | Crowded longs | Block new LONG |
| < -2.0 | Crowded shorts | Block new SHORT |
| -2.0 to 2.0 | Neutral | No restriction |

**Rule**: Don't trade with the crowd when funding is extreme.

### 4. Open Interest Filter

| OI Change (1h) | Price Change | Signal | Action |
|----------------|--------------|--------|--------|
| > 5% | < 0.5% | Squeeze building | Alert LLM |
| < -5% | Any | Positions closing | Reduce confidence |

### 5. Correlation Filter

```python
MAX_CORRELATED_EXPOSURE = 0.5  # Max 50% of capital in correlated assets

CORRELATED_PAIRS = {
    "BTCUSDT": ["ETHUSDT"],
    "ETHUSDT": ["BTCUSDT"],
}
```

**Rule**: If already long BTC, reduce ETH position size by 50%.

### 6. News Event Filter

```python
BLOCKED_EVENTS = [
    "FOMC",
    "CPI",
    "NFP",
    "ECB_RATE",
    "FED_SPEECH"
]

BLOCK_WINDOW_MINUTES = {
    "before": 60,
    "after": 30
}
```

**Rule**: No new positions within block window around major events.

### 7. Minimum Movement Filter

```python
MIN_CANDLE_BODY_ATR_RATIO = 0.3  # Candle body must be at least 30% of ATR
```

**Rule**: Skip "doji" candles with tiny bodies.

### 8. CME Gap Awareness (BTC/ETH Only)

```python
CME_CLOSE_UTC = {"day": "friday", "hour": 21}
CME_OPEN_UTC = {"day": "sunday", "hour": 22}

def get_cme_gap(last_friday_close: float, current_price: float) -> float:
    return (current_price - last_friday_close) / last_friday_close
```

**Rule**: If CME gap exists (>1%), alert LLM that gap fill is possible target/risk.

## Valid Trading Setups (LLM)

The LLM evaluates these setups when all pre-filters pass.

### Setup Types

#### 1. Trend Continuation

**Conditions (Algorithm Pre-Check)**:
- EMA20 > EMA50 > EMA200 (for LONG)
- Price above EMA20
- RSI between 40-70

**LLM Evaluates**:
- Is this a clean pullback to EMA20?
- Is there confluence with a support level?
- Does the pullback show decreasing volume?
- Is there a bullish reversal candle pattern?

#### 2. Breakout

**Conditions (Algorithm Pre-Check)**:
- Price breaking above/below 20-period high/low
- Volume > 1.5x average
- ATR expanding (not contracting)

**LLM Evaluates**:
- Is this a valid consolidation break?
- Is there order flow confirmation (OI increasing)?
- Are there trapped traders to fuel the move?
- What's the quality of the consolidation pattern?

#### 3. Support/Resistance Bounce

**Conditions (Algorithm Pre-Check)**:
- Price within 0.5% of a calculated S/R level
- RSI showing divergence or oversold/overbought
- Not during EXTREME volatility

**LLM Evaluates**:
- How many times has this level held before?
- Is there a clear rejection candle?
- Does order book show absorption at this level?
- What's the risk/reward to the next level?

#### 4. Divergence Trade

**Conditions (Algorithm Pre-Check)**:
- RSI divergence detected algorithmically
- Price at swing high/low
- Trend is mature (20+ candles since last reversal)

**LLM Evaluates**:
- Is this a regular or hidden divergence?
- Is there confluence with a key level?
- What's the broader market context?
- How clean is the divergence pattern?

## Confluence Scoring System

### Algorithm-Calculated Confluence Points

| Signal | Points | Calculation |
|--------|--------|-------------|
| EMA alignment (20>50>200 or reverse) | +1 | Simple comparison |
| RSI in favorable zone (30-40 for LONG, 60-70 for SHORT) | +1 | Threshold check |
| Volume above average | +1 | Ratio calculation |
| Price at Bollinger Band | +1 | Distance check |
| Funding rate favorable | +1 | Threshold check |
| OI supports direction | +1 | Change direction |

**Algorithm Total**: 0-6 points

### LLM-Assessed Confluence Points

| Signal | Points | Assessment |
|--------|--------|------------|
| Chart pattern quality | 0-2 | Pattern clarity |
| Key level proximity | 0-2 | Historical significance |
| Multi-timeframe alignment | 0-2 | Higher TF trend |
| Candle pattern quality | 0-1 | Reversal/continuation signal |
| Market narrative | 0-1 | Story makes sense |

**LLM Total**: 0-8 points

### Combined Score Thresholds

| Total Score | Grade | Position Size | Action |
|-------------|-------|---------------|--------|
| 0-4 | D | 0% | WAIT |
| 5-6 | C | 0% | WAIT |
| 7-8 | B | 50% | Trade (reduced) |
| 9-11 | A | 100% | Trade (full) |
| 12-14 | A+ | 100% | Trade (consider scale-in) |

**Rule**: Minimum 7 points required to trade.

## Entry Rules

### Algorithm-Enforced Entry Rules

| Rule | Check | Enforcement |
|------|-------|-------------|
| Risk per trade | Max 1% of account | Hard block |
| Risk/Reward ratio | Minimum 1.5:1 | Hard block |
| Max positions | 2 concurrent | Hard block |
| Entry deviation | Max 0.5% from suggested | Hard block |
| SL distance | Min 0.5 ATR, Max 3 ATR | Hard block |

### LLM-Suggested Entry Parameters

| Parameter | LLM Provides | Algorithm Validates |
|-----------|--------------|---------------------|
| Entry price | Suggested level | Within 0.5% of current |
| Stop loss | Based on structure | Within ATR limits |
| Take profit | Based on levels | Meets R:R requirement |
| Position management | Trailing/partial settings | Within config bounds |

## Exit Rules

### Algorithm-Managed Exits (Automatic)

| Exit Type | Trigger | Action |
|-----------|---------|--------|
| Stop Loss | Price hits SL | Full exit |
| Take Profit | Price hits TP | Full exit |
| Trailing Stop | Price moves X ATR | Update SL |
| Break-Even | Price moves 1 ATR profit | Move SL to entry |
| Partial Exit | Price at 50% to TP | Exit 30% |
| Time Exit | 24h with < 0.5% move | Close position |
| Drawdown Exit | Account drawdown > 5% | Close all |

### LLM-Suggested Exits

| Scenario | LLM Input | When Asked |
|----------|-----------|------------|
| Early exit | "Setup invalidated" | On position review |
| Hold longer | "Extend TP target" | Near original TP |
| Add to position | "Scale-in opportunity" | On pullback |

**Rule**: LLM can suggest exits, but algorithm enforces all protective exits.

## Symbol Selection

### Algorithm Criteria

| Criteria | Requirement | Check |
|----------|-------------|-------|
| 24h Volume | > $100M USDT | API data |
| Spread | < 0.05% | Order book |
| Binance listing | Active perpetual | API check |
| Manipulation risk | Not meme coin | Whitelist |

### Approved Symbols

```yaml
tier_1:  # Most liquid, primary focus
  - BTCUSDT
  - ETHUSDT

tier_2:  # Good liquidity, secondary
  - BNBUSDT
  - SOLUSDT
  - XRPUSDT

tier_3:  # Trade only with A+ setups
  - DOGEUSDT
  - AVAXUSDT
  - ADAUSDT
```

**Rule**: Tier 3 requires confluence score of 10+.

## Risk Budget

### Daily Limits (Algorithm-Enforced)

| Limit | Value | Action When Hit |
|-------|-------|-----------------|
| Max daily loss | 2% of account | Stop trading for day |
| Max daily trades | 5 | Stop new entries |
| Max consecutive losses | 3 | Pause 4 hours |
| Max winning streak action | After 4 wins | Reduce size 50% |

### Weekly Limits

| Limit | Value | Action When Hit |
|-------|-------|-----------------|
| Max weekly loss | 5% of account | Stop trading for week |
| Max weekly drawdown | 7% | Review with operator |

## Trade Grading (Post-Trade)

### Algorithm-Calculated Metrics

| Metric | Calculation |
|--------|-------------|
| R-Multiple | Profit / Initial Risk |
| Hold Time | Entry to Exit duration |
| MAE | Maximum Adverse Excursion |
| MFE | Maximum Favorable Excursion |
| Slippage | Actual vs Intended prices |

### LLM Post-Trade Review

After each trade closes, log for LLM review:

```python
class TradeReviewSchema(BaseModel):
    trade_id: str
    entry_reasoning: str
    outcome: Literal["WIN", "LOSS", "BREAKEVEN"]
    what_worked: str | None
    what_failed: str | None
    lesson_learned: str | None
    setup_grade_actual: Literal["A", "B", "C", "D"]
```

**Purpose**: Improve future LLM prompts based on actual results.

## Implementation Priority

### Phase 1: Algorithm Filters (Week 1-2)
- [ ] Session filter
- [ ] Volatility regime detector
- [ ] Funding rate filter
- [ ] Position limit enforcement
- [ ] Basic confluence point calculation

### Phase 2: LLM Integration (Week 3-4)
- [ ] Setup type detection prompts
- [ ] Confluence scoring prompts
- [ ] Entry parameter generation
- [ ] Position management instructions

### Phase 3: Feedback Loop (Week 5+)
- [ ] Trade outcome logging
- [ ] Confidence calibration from results
- [ ] Prompt refinement based on grades

## System Prompt Integration

The trading plan rules should be injected into system prompts:

```jinja2
<trading_rules>
Minimum confluence score to trade: 7 points
Valid setup types: Trend Continuation, Breakout, S/R Bounce, Divergence

You are ONLY evaluating LLM-assessed confluence (0-8 points).
Algorithm has pre-calculated {{ algo_confluence_score }} points.
Combined minimum needed: 7 points.
You need to add at least {{ 7 - algo_confluence_score }} points for a trade.

If you cannot justify {{ 7 - algo_confluence_score }}+ points, output WAIT.
</trading_rules>
```

## Summary: Who Does What

```
┌─────────────────────────────────────────────────────────────────┐
│                    DECISION FLOW                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  CANDLE CLOSES                                                   │
│       │                                                          │
│       ▼                                                          │
│  ┌─────────────────────────────────────────┐                    │
│  │        ALGORITHM PRE-FILTERS            │                    │
│  │  • Session check                        │                    │
│  │  • Volatility regime                    │                    │
│  │  • Funding rate filter                  │                    │
│  │  • News event filter                    │                    │
│  │  • Position limits                      │                    │
│  │  • Correlation check                    │                    │
│  └─────────────────┬───────────────────────┘                    │
│                    │                                             │
│           PASS?    ├──── NO ───► SKIP (save LLM cost)           │
│                    │                                             │
│                   YES                                            │
│                    │                                             │
│                    ▼                                             │
│  ┌─────────────────────────────────────────┐                    │
│  │     ALGORITHM CONFLUENCE CALC           │                    │
│  │  • EMA alignment (+1)                   │                    │
│  │  • RSI zone (+1)                        │                    │
│  │  • Volume (+1)                          │                    │
│  │  • Bollinger (+1)                       │                    │
│  │  • Funding favorable (+1)               │                    │
│  │  • OI direction (+1)                    │                    │
│  │  ─────────────────────                  │                    │
│  │  ALGO SCORE: 0-6 points                 │                    │
│  └─────────────────┬───────────────────────┘                    │
│                    │                                             │
│                    ▼                                             │
│  ┌─────────────────────────────────────────┐                    │
│  │           LLM ANALYSIS                  │                    │
│  │  • Pattern recognition (0-2)            │                    │
│  │  • Key level assessment (0-2)           │                    │
│  │  • Multi-TF alignment (0-2)             │                    │
│  │  • Candle pattern (0-1)                 │                    │
│  │  • Market narrative (0-1)               │                    │
│  │  ─────────────────────                  │                    │
│  │  LLM SCORE: 0-8 points                  │                    │
│  └─────────────────┬───────────────────────┘                    │
│                    │                                             │
│                    ▼                                             │
│  ┌─────────────────────────────────────────┐                    │
│  │         COMBINED DECISION               │                    │
│  │  Total = ALGO + LLM                     │                    │
│  │  • < 7: WAIT                            │                    │
│  │  • 7-8: Trade at 50% size               │                    │
│  │  • 9+: Trade at full size               │                    │
│  └─────────────────┬───────────────────────┘                    │
│                    │                                             │
│                    ▼                                             │
│  ┌─────────────────────────────────────────┐                    │
│  │      ALGORITHM EXECUTION                │                    │
│  │  • Position sizing (ATR-based)          │                    │
│  │  • Order placement                      │                    │
│  │  • SL/TP orders                         │                    │
│  │  • Trailing stop management             │                    │
│  │  • Partial exit execution               │                    │
│  └─────────────────────────────────────────┘                    │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Related Documentation

| Document | Purpose |
|----------|---------|
| [02_ARCHITECTURE.md](02_ARCHITECTURE.md) | System design |
| [03_LLM_ARCHITECTURE.md](03_LLM_ARCHITECTURE.md) | LLM integration |
| [05_IMPLEMENTATION_PLAN.md](05_IMPLEMENTATION_PLAN.md) | Build timeline |
| [06_SPINE_IMPLEMENTATION.md](06_SPINE_IMPLEMENTATION.md) | Execution details |
