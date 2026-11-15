# Trend following backtest, rules fixed 2026-11-16 before any code or result

Hypothesis from the literature (Liu & Tsyvinski 2021; Zarattini, Pagani &
Barbon 2025): a volatility-sized Donchian breakout ensemble on daily bars earns
a net Sharpe above buy-and-hold on liquid crypto. Nobody has run a trend rule
on this cache before this file.

## Data

- Daily bars per UTC day, built from the cached 4h candles (6 per day):
  open of the first, max high, min low, close of the last. Days with fewer than
  6 candles are dropped.
- Funding: cached settlements, summed per UTC day.
- Universes: TRADING = BTC ETH SOL XRP BNB ADA LINK AVAX; HOLDOUT = DOGE LTC DOT
  BCH ATOM TRX ETC FIL (USDT perps). Each is scored on its own.
- Window: returns from 2022-03-15 to 2026-11-14 inclusive. Earlier days only
  warm up lookbacks.

## Rule (primary: long/flat)

- For each lookback L in {20, 40, 80} days: state_L(t) = 1 if close_t is above
  the highest close of days t-L..t-1, 0 if below the lowest close of those
  days, else state_L(t-1). Start at 0.
- signal(t) = mean of the three states, in [0, 1].
- vol(t) = std of the last 30 daily log returns x sqrt(365).
- target weight w(t) = signal(t) x min(0.25 / vol(t), 2.0) / N, where N = 8.
- Weights are set at the close of day t and earn the close-to-close return of
  day t+1. No information after close t is used.
- Turnover buffer: a symbol is traded only when its target is zero or changes
  sign, or differs from the held weight by more than 20% of the held weight.
- Costs: 0.0005 (`paper.commission_rate`) x |traded weight| per trade.
  Funding: held weight x day t+1 funding sum (a long pays positive funding).

## Benchmark

Equal-weight buy-and-hold of the same universe (1/N each, daily rebalanced,
no costs, no funding).

## Report, per universe

Annualised net return, volatility, Sharpe (daily, x sqrt(365)), max drawdown,
turnover per year, cost and funding drag, Sharpe per calendar year, and the
same for the benchmark.

## Decision

- PASS: net Sharpe >= 0.5 on BOTH universes AND net Sharpe above the
  benchmark's on BOTH.
- Anything else is FAIL.
- Exploratory only, not part of the decision: the long/short variant (-1
  instead of 0 below the low) and each lookback on its own.
- No parameter in this file may change after the first run.
