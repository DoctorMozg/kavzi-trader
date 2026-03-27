# The Software Engineer's Guide to Crypto Trading

Everything you need to understand the trading concepts behind KavziTrader, explained for
someone who has never traded before. No finance degree required.

---

## Table of Contents

1. [Trading Fundamentals](#1-trading-fundamentals)
2. [Technical Indicators](#2-technical-indicators)
3. [Order Flow Metrics](#3-order-flow-metrics)
4. [Derived Concepts](#4-derived-concepts)
5. [Risk Management](#5-risk-management)
6. [Pre-Trade Filters](#6-pre-trade-filters)
7. [Position Management](#7-position-management)
8. [The Decision Pipeline](#8-the-decision-pipeline)

---

## 1. Trading Fundamentals

### What Is a Candlestick?

A candlestick is a data structure representing price movement over a fixed time period (e.g.,
5 minutes, 1 hour, 4 hours). Each candle has five fields, collectively called **OHLCV**:

| Field    | Meaning                              |
|----------|--------------------------------------|
| **Open** | Price at the start of the period     |
| **High** | Highest price reached during the period |
| **Low**  | Lowest price reached during the period  |
| **Close**| Price at the end of the period       |
| **Volume** | Total amount traded during the period |

The **body** of the candle is the range between Open and Close. If Close > Open, the candle
is "bullish" (price went up). If Close < Open, the candle is "bearish" (price went down).
The thin lines above and below the body are called **wicks** (or shadows) and show the
High/Low extremes.

Think of each candle as a log entry: it tells you where things started, the extremes, and
where they ended up.

### Long vs Short

**Going long** means you buy an asset expecting the price to go up. You profit when the
price rises and lose when it falls. This is what most people think of as "buying."

**Going short** means you sell an asset you don't own (borrowed from the exchange) expecting
the price to go down. You profit when the price drops and lose when it rises. This is the
equivalent of betting against the asset.

In software terms: long = `profit = (sell_price - buy_price)`, short =
`profit = (sell_price - buy_price)` but you sell first and buy back later.

### Leverage and Margin

**Leverage** lets you control a larger position than your account balance by borrowing from
the exchange. If you have $100 and use **3x leverage**, you control $300 worth of crypto.

- Gains are amplified: a 10% price increase yields 30% profit on your $100.
- Losses are equally amplified: a 10% price decrease causes a 30% loss.

**Margin** is the collateral you put up. There are two types:

- **Isolated margin**: Each position has its own separate collateral. If one trade goes bad,
  only that position's margin is lost. The rest of your account is safe.
- **Cross margin**: All positions share the entire account balance as collateral. A big loss
  on one trade can drain the whole account.

This system uses **isolated margin at 3x leverage** by default. Think of isolated margin as
running each service in its own container — failures are isolated.

### Liquidation

When your losses on a leveraged position approach the margin you deposited, the exchange
force-closes your position. This is **liquidation** — the exchange's circuit breaker to
prevent you from owing them money.

The approximate liquidation price:

- **Long**: `liquidation_price = entry_price × (1 - 1/leverage)`
- **Short**: `liquidation_price = entry_price × (1 + 1/leverage)`

Example: You go long at $1,000 with 3x leverage.
Liquidation price ≈ $1,000 × (1 - 1/3) = **$667**. If the price drops 33% to $667, your
position is liquidated and you lose your entire margin for that trade.

In practice, exchanges liquidate slightly before the theoretical price due to a **maintenance
margin** buffer. The real threshold at 3x is closer to a 28-30% adverse move, not a full 33%.

### Stop-Loss and Take-Profit

A **stop-loss (SL)** is a pre-set order that automatically closes your position if the price
moves against you past a threshold. It caps your maximum loss on a trade.

- Long position: SL is placed **below** the entry price.
- Short position: SL is placed **above** the entry price.

A **take-profit (TP)** is a pre-set order that automatically closes your position when price
reaches your target profit level.

- Long position: TP is placed **above** the entry price.
- Short position: TP is placed **below** the entry price.

Together, SL and TP define the full risk/reward envelope of a trade. Think of them as
assertion bounds — if the value goes outside the expected range, the system exits
automatically.

Note: Stop-loss orders are typically "stop-market" orders, meaning they trigger a market
order when the stop price is hit. In fast-moving markets, the actual fill price can be
slightly worse than the stop price. This is called **slippage**.

### Risk-Reward Ratio

The **risk-reward ratio (R:R)** measures how much you stand to gain versus how much you
risk losing. In this system, it is defined as:

```
R:R = (distance to take-profit) / (distance to stop-loss)
```

A **2:1 R:R** means you stand to gain $2 for every $1 you risk. Higher is better.

This system requires a **minimum R:R of 1.5:1**. If a trade setup cannot achieve at least
$1.50 of potential reward for every $1 of risk, it is rejected.

Important nuance: R:R must be evaluated alongside **win rate**. A 3:1 ratio with a 20% win
rate loses money. A 1.5:1 ratio with a 60% win rate is profitable. The minimum threshold
exists because the system targets setups with reasonable win rates.

### Perpetual Futures

Traditional futures contracts have an **expiry date** — they settle at a fixed future date.
**Perpetual futures** (or "perps") are crypto-specific contracts that **never expire**. You
can hold them indefinitely.

Since there is no expiry to force the contract price toward the real (spot) price, perps use
a mechanism called the **funding rate** to keep them anchored.

### Funding Rate

The **funding rate** is a periodic payment between long and short holders, settled every
**8 hours** on Binance (at 00:00, 08:00, and 16:00 UTC).

- **Positive funding rate**: Longs pay shorts. This means the market is bullish-biased — more
  people want to be long, so longs pay a premium. Economically favorable for shorts (they
  earn income).
- **Negative funding rate**: Shorts pay longs. The market is bearish-biased. Favorable for
  longs.

Think of it as a supply-and-demand rebalancing fee. If too many people are long, the cost of
being long increases, incentivizing some to close and bringing the perp price back toward
spot.

The baseline rate on Binance is 0.01% per 8-hour interval, but it fluctuates based on how
far the perp price deviates from spot. In volatile markets, it can spike much higher.

At 0.03% per 8 hours with 3x leverage, holding a position for 24 hours costs approximately
**0.27% of position value** in funding payments. This is a real cost that erodes profits on
longer holds.

---

## 2. Technical Indicators

Technical indicators are mathematical formulas applied to price and volume data to extract
signals about trend, momentum, and volatility. The system calculates these from raw
candlestick data and feeds them to the AI agents.

### EMA — Exponential Moving Average

**What it is**: A weighted average of recent prices where more recent prices get
exponentially higher weight. It reacts faster to price changes than a simple average.

**The system calculates three EMAs**:
- **EMA-20** (short-term): Reacts fastest. Captures the immediate trend.
- **EMA-50** (medium-term): Smooths out noise. Shows the intermediate trend.
- **EMA-200** (long-term): Very smooth. Shows the major trend direction.

**How it is used**: The relative order of these three EMAs reveals trend alignment:
- **Bullish alignment**: EMA-20 > EMA-50 > EMA-200 (uptrend at all timeframes)
- **Bearish alignment**: EMA-20 < EMA-50 < EMA-200 (downtrend at all timeframes)
- **Mixed**: EMAs are out of order (no clear trend)

EMAs also act as dynamic support/resistance — price often bounces off them during trends.

### SMA — Simple Moving Average

**What it is**: The arithmetic mean of closing prices over N periods. All data points have
equal weight, so it reacts more slowly than EMA.

**How it is used**: Primarily as the middle band in Bollinger Bands (20-period SMA). Less
commonly used for trend detection because EMA responds faster.

### RSI — Relative Strength Index

**What it is**: A momentum oscillator that measures the speed and magnitude of recent price
changes. Ranges from 0 to 100.

**Formula**: `RSI = 100 - (100 / (1 + RS))` where `RS = average_gain / average_loss` over
14 periods.

**How to read it**:
- **RSI > 70**: Overbought — the asset has risen fast and may pull back.
- **RSI < 30**: Oversold — the asset has fallen fast and may bounce.
- **RSI = 50**: Neutral momentum.

**How the system uses it for confluence scoring**:
- For a **long** trade with aligned EMAs: RSI should be 50-70 (trending up, not yet
  overbought).
- For a **long** trade without aligned EMAs: RSI should be 30-40 (recovering from oversold
  — potential reversal entry).
- Mirror logic applies for shorts.

**Important caveat**: RSI can remain overbought or oversold for extended periods during
strong trends. An RSI of 75 does not guarantee a reversal — in a strong uptrend, it can stay
above 70 for days. It is a signal to be cautious, not an automatic sell trigger.

### MACD — Moving Average Convergence Divergence

**What it is**: A momentum indicator that shows the relationship between two EMAs of
different speeds.

**Components**:
- **MACD Line**: EMA(12) - EMA(26) — the difference between a fast and slow moving average.
- **Signal Line**: EMA(9) of the MACD line — a smoothed version of the MACD.
- **Histogram**: MACD Line - Signal Line — visualizes the gap between them.

**How to read it**:
- MACD crosses **above** Signal = bullish momentum is building.
- MACD crosses **below** Signal = bearish momentum is building.
- Expanding histogram = momentum is accelerating.
- Shrinking histogram = momentum is fading.

**Important caveat**: MACD is a **lagging indicator**. By the time it confirms a trend, the
move may already be partially or fully complete. It is better at confirming trends than
predicting them.

### ATR — Average True Range

**What it is**: A measure of price volatility — how much the price typically moves in a
single period. It measures the magnitude of movement, not the direction.

**Formula**: True Range = max(High - Low, |High - PrevClose|, |Low - PrevClose|). ATR is the
exponential moving average of True Range over 14 periods.

The True Range formula captures **gap** movements — situations where the current candle's
range doesn't overlap with the previous candle's close (common after news events).

**How to read it**:
- **High ATR**: The market is volatile, expect large price swings.
- **Low ATR**: The market is calm, expect small movements.
- **Rising ATR**: Volatility is increasing (often during breakouts or crashes).
- **Falling ATR**: Volatility is decreasing (often during consolidation).

**How the system uses ATR** (this is the most important indicator in the system):
- **Stop-loss sizing**: SL is placed at a multiple of ATR from entry (min 0.5 ATR, max
  3.0 ATR). This adapts the stop distance to current market conditions.
- **Position sizing**: Risk per trade is calculated as `account_balance × 1% / (ATR × SL_multiplier)`.
- **Trailing stops**: Trail at 1.5 ATR behind the current price.
- **Break-even trigger**: Move SL to entry after 1.0 ATR of profit.
- **Volatility regime detection**: ATR Z-score classifies the market as LOW, NORMAL, HIGH,
  or EXTREME (more on this later).

Think of ATR as the standard deviation of price movement — it tells you what "normal" looks
like so the system can calibrate its expectations.

### Bollinger Bands

**What they are**: An envelope around a moving average that expands and contracts with
volatility.

**Components**:
- **Middle Band**: 20-period SMA.
- **Upper Band**: Middle + (2 × standard deviation).
- **Lower Band**: Middle - (2 × standard deviation).
- **%B**: `(current_price - lower) / (upper - lower)` — where price sits within the bands.
  0 = at the lower band, 1 = at the upper band. Values outside 0-1 mean price has broken
  through.
- **Band Width**: `(upper - lower) / middle` — measures how wide the bands are.

**How to read them**:
- Price near **upper band**: Potentially overbought, may pull back.
- Price near **lower band**: Potentially oversold, may bounce.
- **Narrow bands**: Low volatility, a big move may be coming (the "squeeze").
- **Wide bands**: High volatility, the market is active.

**How the system uses them for confluence scoring**:
- For a **long** trade: price at or below the lower band = strong buy signal. Or, if EMAs
  are bullish-aligned and price is at the upper band = trend continuation signal.
- For a **short** trade: price at or above the upper band = strong sell signal. Or, if EMAs
  are bearish-aligned and price is at the lower band = trend continuation signal.

### Volume Ratio

**What it is**: Current period's volume divided by the average volume over 20 periods. It
tells you whether current trading activity is above or below normal.

**How to read it**:
- **> 1.5**: High volume — strong conviction behind the current move.
- **0.8 - 1.2**: Normal volume.
- **< 0.5**: Low volume — weak conviction, the move may not sustain.
- **> 2.5**: Volume spike — exceptional activity, often signals a breakout or capitulation.

**How the system uses it**:
- Volume ratio > 1.0 earns a confluence point ("volume above average").
- Volume ratio > 2.5 earns an additional confluence point ("volume spike").
- Low volume (< 0.8) is a strong reason for the Scout agent to skip a candle.

### OBV — On-Balance Volume

**What it is**: A cumulative indicator that adds volume on up-candles and subtracts volume on
down-candles. It tracks whether volume is flowing into (accumulation) or out of
(distribution) an asset.

**How to read it**:
- **Rising OBV**: Buyers are dominant — volume flows in on up moves.
- **Falling OBV**: Sellers are dominant — volume flows in on down moves.
- **Divergence**: If price makes a new high but OBV does not, buying pressure is weakening.
  This divergence often precedes a reversal.

OBV is passed to the AI agents as part of the volume analysis context to help them assess
whether the current price move has real conviction behind it.

---

## 3. Order Flow Metrics

Order flow data comes from the exchange's futures market and provides insight into what other
traders are doing — their positioning, their leverage, and their crowding. While technical
indicators analyze price and volume, order flow analyzes the people trading.

### Funding Rate (Raw)

Already covered in fundamentals. The raw rate is the per-interval payment percentage. The
system fetches this from Binance's API.

### Funding Z-Score

**What it is**: The funding rate standardized against its own recent history using a Z-score
(how many standard deviations from the mean).

**Formula**: `z = (current_funding - mean_30) / stdev_30` over 30 periods.

**How to read it**:
- **Z > 2.0**: Extremely crowded long. Too many people are paying to be long. This is a
  bearish signal — the crowd is vulnerable to a **long squeeze**.
- **Z < -2.0**: Extremely crowded short. Too many people are paying to be short. Bullish
  signal — vulnerable to a **short squeeze**.
- **Z between -1.0 and 1.0**: Neutral positioning.

**How the system uses it**:
- **Confluence scoring**: Funding z-score <= 0 is favorable for longs (you earn funding or
  at least don't pay much). Z-score >= 0 is favorable for shorts.
- **Filter**: Blocks long trades when z > 2.0 (crowded long). Blocks short trades when
  z < -2.0 (crowded short). Reduces position size by 20% when z is moderately adverse
  (1.0-2.0 range).

Note: The ±2.0 thresholds are calibrated heuristics, not universal constants. Crypto funding
distributions have heavier tails than a normal distribution, so extreme readings can occur
more often than the "95% rule" would suggest.

### Open Interest (OI)

**What it is**: The total value of all outstanding futures contracts that haven't been closed
or settled. Unlike volume (which counts transactions), OI counts how many contracts are still
open.

Think of it as the number of active connections in a connection pool, vs volume being the
request throughput.

**1-Hour OI Change** (oi_change_1h_percent): How much OI has changed in the last hour.
**24-Hour OI Change** (oi_change_24h_percent): How much OI has changed in the last 24 hours.

**The OI / Price Matrix** (these are probabilistic tendencies, not guarantees):

| OI Trend | Price Trend | Interpretation |
|----------|-------------|----------------|
| Rising   | Rising      | New longs entering — bullish confirmation |
| Rising   | Falling     | New shorts entering — bearish confirmation |
| Falling  | Rising      | Short covering (shorts closing) — weak rally, not confirmed by new money |
| Falling  | Falling     | Long liquidation (longs closing) — weak decline, positions unwinding |

**How the system uses it**: 1-hour OI change > 0 earns a confluence point for longs. OI
change < 0 earns a confluence point for shorts.

### Squeeze Alert

**What it is**: A computed flag that triggers when OI is changing significantly (> 5%) but
price is barely moving (< 0.5%). This indicates a potential **squeeze** is building.

A squeeze is when a crowded position gets forced out:
- **Long squeeze**: Price drops, triggering stop-losses and liquidations of long holders.
  Each wave of forced selling pushes price lower, triggering more liquidations. It cascades.
- **Short squeeze**: Price rises, forcing short holders to buy back. Each wave of forced
  buying pushes price higher, triggering more liquidations.

In crypto, exchange liquidation engines close positions using **market orders**, which means
they buy or sell at whatever price is available. This forced execution is what creates the
cascading effect that distinguishes crypto squeezes from traditional market squeezes.

When the squeeze alert fires, it means there is a lot of positioning happening without
directional commitment — like pressure building behind a dam.

### Long/Short Ratio

**What it is**: The ratio of accounts holding long positions to those holding short positions.

- **> 1.0**: More longs than shorts (bullish bias among retail traders).
- **< 1.0**: More shorts than longs (bearish bias).
- **> 2.0 or < 0.5**: Crowded — an extreme imbalance that may precede a mean-reversion move.

Note: What counts as "crowded" varies by asset. Bitcoin historically skews slightly long even
in neutral conditions, so a BTC long/short ratio of 1.2 might be normal while for another
asset it would signal crowding.

---

## 4. Derived Concepts

These are system-specific abstractions built on top of the raw indicators and order flow data.

### Volatility Regimes

The system classifies the current market into one of four **volatility regimes** based on the
ATR Z-score (how unusual current volatility is compared to the last 30 periods):

| Regime     | ATR Z-Score    | Tradeable? | Position Size Multiplier |
|------------|----------------|------------|-------------------------|
| **LOW**    | Z < -1.5       | No         | 0x (no trades)          |
| **NORMAL** | -1.5 to 1.0    | Yes        | 1.0x (full size)        |
| **HIGH**   | 1.0 to 2.0     | Yes        | 0.5x (half size)        |
| **EXTREME**| Z > 2.0        | No         | 0x (no trades)          |

**Why this matters**:
- **LOW volatility** (Z < -1.5): The market is too quiet. Stop-losses would be so tight that
  normal noise triggers them. Not worth trading.
- **NORMAL**: Standard conditions. The system trades at full capacity.
- **HIGH**: Elevated volatility. Trades are allowed but positions are automatically halved
  to reduce risk. Stop-losses are widened (1.5-2.0 ATR instead of 1.0-1.5 ATR).
- **EXTREME**: Dangerous conditions (market crash, flash spike, major news). The system
  refuses to trade entirely.

Think of this as a circuit breaker pattern: the system sheds load (reduces position size) or
trips entirely (refuses to trade) when conditions are abnormal.

### Confluence Scoring

**Confluence** means multiple independent signals agreeing on the same direction. The more
signals that align, the higher the probability that the trade setup is valid.

The system computes confluence for both long and short directions independently, then picks
the stronger one.

**7 algorithmic signals** (binary, 0 or 1 point each):

| # | Signal | Long Condition | Short Condition |
|---|--------|----------------|-----------------|
| 1 | EMA Alignment | EMA20 > EMA50 > EMA200 | EMA20 < EMA50 < EMA200 |
| 2 | RSI Favorable | RSI 50-70 (aligned) or 30-40 (not aligned) | RSI 30-50 (aligned) or 60-70 (not aligned) |
| 3 | Volume Above Average | Volume ratio > 1.0 | Volume ratio > 1.0 |
| 4 | Price at Bollinger | At lower band, or upper band + aligned | At upper band, or lower band + aligned |
| 5 | Funding Favorable | Funding Z-score <= 0 | Funding Z-score >= 0 |
| 6 | OI Supports Direction | 1h OI change > 0% | 1h OI change < 0% |
| 7 | Volume Spike | Volume ratio > 2.5 | Volume ratio > 2.5 |

**Up to 4 discretionary points** (added by the Analyst AI agent):
- +1 if funding rate magnitude/context strongly supports direction (beyond the binary signal).
- +1 if OI trend confirms direction with additional context.
- +1 if price is at a key support/resistance level.
- +1 if candle pattern confirms direction.

**Total possible: 11 points** (7 algorithmic + 4 discretionary).

**Minimum threshold: 7 points** required for the Analyst to mark a setup as valid.

### Confidence Calibration

The Trader AI agent outputs a raw confidence score (0.0 to 1.0) for each trade decision.
The problem: LLMs tend to be overconfident. A model saying "I'm 90% confident" is often
actually correct far less than 90% of the time.

**Calibration** adjusts the raw confidence based on historical accuracy:

| Raw Confidence Range | Default Calibrated Value |
|---------------------|-------------------------|
| 0.90 - 1.00        | 0.65                    |
| 0.80 - 0.89        | 0.55                    |
| 0.70 - 0.79        | 0.45                    |
| Below 0.70          | 0.35                    |

The system tracks actual trade outcomes in Redis, recording whether trades at each confidence
bucket actually won or lost. Over time, the calibrated values converge toward true accuracy.

**Threshold**: If calibrated confidence is below 0.5, the system outputs WAIT (no trade).

### Staleness

A trade decision has a **shelf life**. The faster the market moves, the quicker a decision
becomes stale. The system enforces freshness checks before executing any trade:

| Volatility Regime | Max Decision Age | Rationale |
|-------------------|-----------------|-----------|
| LOW               | 60 seconds      | Slow market, decisions stay relevant longer |
| NORMAL            | 30 seconds      | Standard freshness |
| HIGH              | 15 seconds      | Fast market, conditions change quickly |
| EXTREME           | 5 seconds       | Spiking market, almost any decision is immediately outdated |

If a decision is older than the threshold when execution attempts to place the order, it is
marked EXPIRED and discarded. Think of it as a TTL on a cache entry.

---

## 5. Risk Management

Risk management determines how much to risk on each trade and when to stop trading entirely.

### Position Sizing

The system calculates position size using a formula that ties risk to ATR:

```
risk_amount = account_balance × (risk_per_trade_percent / 100)
base_size = risk_amount / (ATR × stop_loss_atr_multiplier)
adjusted_size = base_size × regime_multiplier × liquidity_multiplier × correlation_multiplier
```

With the default config (`risk_per_trade_percent = 1.0`): you risk 1% of your account on
each trade. If your account is $10,000, you risk $100 per trade. The actual position size is
calculated so that if the stop-loss is hit, you lose exactly that $100 (adjusted for
volatility regime, liquidity, and correlation).

The final size is clamped to not exceed available margin.

### Drawdown Thresholds

**Drawdown** is the percentage decline from the highest recorded account balance (the peak)
to the current balance. It measures how much you have lost from your best point.

Example: Account peaked at $10,000, currently at $9,500. Drawdown = 5%, even if the account
was at $9,200 earlier and has recovered to $9,500. The drawdown is measured from the peak,
not from the worst point.

The system enforces two thresholds:

| Drawdown | Action | Analogy |
|----------|--------|---------|
| **> 3%** | Pause new trades. Existing positions are held. | Rate limiter — stop opening new connections |
| **> 5%** | Emergency close ALL positions. Full stop. | Circuit breaker tripped — shut everything down |

Additionally, for each 1% of drawdown, the system scales confidence down by 0.1, making it
progressively harder to enter new trades as losses accumulate.

### Exposure Limits

- **Maximum concurrent positions**: 2 (configurable). The system will not open a third
  position regardless of the setup quality.
- **No duplicate symbols**: Only one position per trading pair (e.g., only one BTCUSDT
  position at a time).

### Stop-Loss Validation

Every trade must pass these stop-loss checks:

- **Minimum SL distance**: 0.5 ATR. Prevents stops so tight that normal price noise triggers
  them.
- **Maximum SL distance**: 3.0 ATR. Prevents stops so wide that a single loss is
  devastating.
- **Directional check**: SL must be below entry for longs, above entry for shorts.
- **Liquidation safety**: SL distance must be less than 50% of the distance to the
  liquidation price. This ensures you are stopped out well before the exchange would
  liquidate you.

### Risk-Reward Validation

The R:R ratio must be >= 1.5:1. If the distance to the take-profit target is not at least
1.5 times the distance to the stop-loss, the trade is rejected.

### Margin Ratio Check

If the maintenance margin ratio exceeds 0.5 (50% of margin balance is tied up in maintenance
requirements), new trades are blocked. This prevents over-leveraging the account.

---

## 6. Pre-Trade Filters

Before a trade signal reaches execution, it passes through a sequential filter chain. Each
filter can either **reject** the trade or **reduce** the position size. Early rejections
short-circuit the chain (like middleware in a web framework).

### Volatility Filter

Blocks trades in LOW or EXTREME volatility regimes. Only NORMAL and HIGH pass through. This
is the first check in the chain.

### News Event Filter

Blocks trades during scheduled high-impact economic events (Fed announcements, CPI releases,
etc.). The blackout window is:

- **60 minutes before** the event.
- **30 minutes after** the event.

Total blackout: 90 minutes per event. Prevents entering positions when the market is about to
be disrupted by external information that technical analysis cannot predict.

### Funding Rate Filter

- **Blocks** long trades when funding Z-score > 2.0 (crowded long).
- **Blocks** short trades when funding Z-score < -2.0 (crowded short).
- **Reduces** position size by 20% when funding is moderately adverse (Z-score 1.0-2.0
  against your direction).

### Minimum Movement Filter

Rejects candles where the body (|close - open|) is less than **0.3 ATR**. Small-bodied
candles (dojis) indicate indecision, not a directional signal. Trading on them is like making
decisions based on noise.

### Liquidity Filter

Position size is scaled based on the time of day and day of week, reflecting expected market
liquidity. Less liquidity means wider spreads and more slippage, so the system trades
smaller.

**Time-of-day sessions (UTC)**:

| Time (UTC) | Liquidity | Size Multiplier |
|------------|-----------|-----------------|
| 13:00-21:00 | HIGH | 1.0x (full) |
| 07:00-13:00 | MEDIUM | 0.8x |
| 21:00-01:00 | MEDIUM | 0.8x |
| 01:00-07:00 | LOW | 0.5x (half) |

**Weekend adjustments**:
- Saturday: 0.5x multiplier.
- Sunday before 20:00 UTC: 0.5x multiplier.
- Sunday after 20:00 UTC: 0.8x (markets start picking up from Asian pre-open).

### Correlation Filter

Some assets move together. BTC and ETH are highly correlated — when BTC drops, ETH usually
drops too. Holding long positions in both is a concentrated bet on the same direction.

If you already have a position in a correlated asset (e.g., BTCUSDT) and try to open one in
another (e.g., ETHUSDT), the system reduces the new position size by **50%** to limit
correlated exposure.

Configured pairs: `BTCUSDT <-> ETHUSDT`.

---

## 7. Position Management

Once a trade is open, the system actively manages it through several mechanisms, evaluated
every few seconds in priority order.

### Liquidation Emergency

**Trigger**: Position is within 5% of its liquidation price.
**Action**: Force close the entire position immediately.

This is the nuclear option — it fires before any other check. Prevents actual liquidation by
the exchange, which would result in additional liquidation fees.

### Time Exit

**Trigger**: Position has been open longer than 24 hours (configurable per trade).
**Action**: Force close the entire position.

Prevents capital from being locked in trades that are going nowhere. Stale positions also
accumulate funding costs. Think of it as a request timeout — if the trade has not reached its
target in a reasonable time, cut it.

The Trader AI agent sets this dynamically based on timeframe:
- 15-minute candles: 4-12 hour max hold.
- 1-hour candles: 12-48 hour max hold.
- 4-hour candles: 24-96 hour max hold.

### Trailing Stop

**Trigger**: Position has moved 2.0 ATR in profit.
**Action**: Move the stop-loss to trail behind the current price at 1.5 ATR distance.

As price continues to move favorably, the trailing stop ratchets up (for longs) or down (for
shorts), locking in progressively more profit. It never moves backwards — if the price
reverses, the stop stays at its highest point and eventually gets hit.

Example (long at $1,000, ATR = $50):
- Price reaches $1,100 (2 ATR profit) → trailing stop activates.
- Stop moves to $1,100 - (1.5 × $50) = $1,025.
- Price reaches $1,200 → stop moves to $1,200 - $75 = $1,125.
- Price reverses to $1,125 → stop is hit, position closed at ~$1,125 profit.

### Break-Even Move

**Trigger**: Position has moved 1.0 ATR in profit AND trailing stop has not yet activated.
**Action**: Move the stop-loss to the entry price. One-time action.

This eliminates downside risk on the trade — the worst that can happen is breaking even (plus
or minus slippage and fees). It fires before the trailing stop's 2.0 ATR threshold, providing
earlier protection.

### Partial Exit

**Trigger**: Price has reached 50% of the way from entry to take-profit AND partial exit has
not already been taken.
**Action**: Close 30% of the position, locking in partial profit. One-time action.

This is the "take some chips off the table" pattern. Even if the remaining 70% eventually
hits the stop-loss, you have already secured some profit.

### Scale-In (Disabled by Default)

**Trigger**: Position is profitable but price has retraced within 0.5 ATR of entry.
**Action**: Add up to 50% more to the position size (max 1.5x original).

Scale-in is only enabled when `scale_in_allowed = true`, which requires a confluence score
of 8+ and a strong trend. It is disabled by default because adding to positions increases
risk.

---

## 8. The Decision Pipeline

All of the concepts above come together in a three-stage AI pipeline. Each stage acts as a
progressively more expensive filter.

### Stage 1: Scout (Fast Triage)

**Model**: DeepSeek Chat v3 (cheap, ~500ms)
**Input**: Recent candles, technical indicators, volatility regime.
**Output**: INTERESTING or SKIP.

The Scout is a binary gate. It scans every candle close and quickly decides: "Is there
anything here worth investigating?" It looks for any of these patterns:

1. **Breakout**: Price closes beyond a Bollinger Band with volume ratio > 1.2.
2. **Trend continuation**: EMAs aligned, RSI 40-60, volume above average.
3. **Reversal signal**: RSI extreme (< 30 or > 70) with price near a Bollinger boundary.
4. **Volume spike**: Volume ratio > 2.0 with a large candle body and at least one
   supporting signal.
5. **Momentum shift**: MACD histogram changes sign.
6. **Trend with pullback**: EMAs aligned, price moving > 0.5% in the trend direction.

If none of these criteria are met, or if volatility is EXTREME, the Scout outputs SKIP.

**Purpose**: Filter out 90%+ of candles before spending money on the more expensive Analyst.

### Stage 2: Analyst (Setup Validation)

**Model**: GPT-5.4 Mini (mid-tier, ~2s)
**Input**: Everything the Scout got, plus order flow data, algorithm confluence scores, and
leverage information.
**Output**: setup_valid (boolean), direction (LONG/SHORT/NEUTRAL), confluence_score (0-11),
key_levels (support/resistance prices), reasoning.

The Analyst performs deep technical analysis. It:
- Reviews the 7 algorithmic confluence signals.
- Adds up to 4 discretionary points based on order flow context and price structure.
- Identifies key support and resistance levels.
- Validates that the overall setup merits a trade.

**Gate**: setup_valid is only true if confluence_score >= 7 AND volatility regime is
NORMAL or HIGH. This filters out another large chunk of signals.

### Stage 3: Trader (Final Decision)

**Model**: Claude Opus 4.6 (most capable, ~5s)
**Input**: Everything the Analyst got, plus account state (balance, drawdown, margin), open
positions, and the Analyst's full analysis.
**Output**: action (LONG/SHORT/WAIT/CLOSE), entry/SL/TP prices, confidence (0.0-1.0),
position management parameters, reasoning.

The Trader makes the final call. It:
- Reviews the Analyst's direction and key levels.
- Computes precise entry, stop-loss, and take-profit prices.
- Validates R:R >= 1.5:1.
- Sets position management parameters (trailing stop distance, break-even trigger, partial
  exit levels, max hold time).
- Assesses confidence on a 0.0-1.0 scale.
- Checks drawdown and margin constraints.

**Gate**: If confidence < 0.5, outputs WAIT. If R:R < 1.5:1, outputs WAIT. If drawdown
> 3%, outputs WAIT. If drawdown > 5%, outputs CLOSE (all positions).

### After the Pipeline

If the Trader outputs LONG or SHORT, the signal passes through:

1. **Pre-trade filter chain** (volatility, news, funding, movement, exposure, liquidity,
   correlation).
2. **Risk validation** (SL range, R:R, liquidation distance, margin).
3. **Position sizing** (ATR-based, adjusted by all multipliers).
4. **Staleness check** (is the decision still fresh enough?).
5. **Execution** (place entry order with immediate SL and TP on Binance).
6. **Position management loop** (trailing stops, break-even, partial exits, time exits).

The entire flow — from candle close to order placed — targets under 10 seconds for the
common case.

---

## Glossary

| Term | Definition |
|------|-----------|
| **ATR** | Average True Range — measures typical price movement per period |
| **Bollinger Bands** | Price envelope around a moving average, widens with volatility |
| **Confluence** | Multiple independent signals agreeing on the same trade direction |
| **Drawdown** | Peak-to-trough decline in account balance before a new high is reached |
| **EMA** | Exponential Moving Average — trend indicator weighted toward recent prices |
| **Funding Rate** | Periodic payment between long/short holders in perpetual futures |
| **Leverage** | Borrowing to amplify position size (and both gains and losses) |
| **Liquidation** | Exchange force-closing a position when losses approach deposited margin |
| **MACD** | Moving Average Convergence Divergence — momentum indicator |
| **Margin** | Collateral deposited to hold a leveraged position |
| **OBV** | On-Balance Volume — cumulative volume weighted by price direction |
| **OI** | Open Interest — total outstanding futures contracts |
| **R:R** | Risk-Reward Ratio — potential profit / potential loss (higher is better) |
| **RSI** | Relative Strength Index — momentum oscillator (0-100) |
| **SL** | Stop-Loss — automatic exit on adverse price move |
| **SMA** | Simple Moving Average — equal-weight price average |
| **Squeeze** | Cascading forced exits when a crowded position gets overwhelmed |
| **TP** | Take-Profit — automatic exit at target price |
| **Z-score** | Number of standard deviations from the mean — measures how unusual a value is |
