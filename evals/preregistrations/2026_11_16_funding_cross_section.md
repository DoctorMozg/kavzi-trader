# Cross-sectional funding backtest, rules fixed 2026-11-16 before any code or result

Hypothesis (Robot Wealth 2025 on Binance, frictionless; BIS WP 1087): perps
with the highest recent funding underperform those with the lowest over the
next days, and the short side also collects the funding.

## Data

- Universe: all 16 cached USDT perps, BTC ETH SOL XRP BNB ADA LINK AVAX DOGE
  LTC DOT BCH ATOM TRX ETC FIL, as one cross-section.
- Prices: close of the 4h candle ending at 00:00 UTC each day.
- Funding: cached settlements.
- Window: returns from 2022-03-15 to 2026-11-14 inclusive.

## Rule (primary)

- Rebalance at 00:00 UTC every third day, counted from 2022-03-15 (day index
  mod 3 == 0). Holding periods don't overlap.
- Score = mean of each symbol's last 9 funding settlements (3 days) before the
  rebalance time.
- Short the 3 highest scores and long the 3 lowest, each 1/6 of equity:
  gross 1.0, net 0.
- P&L: price return of each leg over the 3 days plus funding settled during
  the hold (a short receives positive funding, a long pays it).
- Costs: 0.0005 (`paper.commission_rate`) x |weight change| at each
  rebalance.

## Report

Annualised net return, volatility, Sharpe (daily marks, x sqrt(365)), max
drawdown, turnover; the price and funding components separately; gross vs net;
net return per calendar year.

## Decision

- PASS: net Sharpe >= 0.5 AND net annualised return > 0 over the whole window
  AND net return > 0 in at least 3 of the 5 calendar years (2022 and 2026
  partial).
- Anything else is FAIL.
- Exploratory only: 1-day hold; top/bottom 2.
- No parameter in this file may change after the first run.
