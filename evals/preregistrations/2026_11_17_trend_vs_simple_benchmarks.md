# Trend vs simpler benchmarks, rules fixed 2026-11-17

A 2026 practitioner study (Summitward, BTC/ETH/SOL 2017–2025) found that vol
scaling, not the trend signal, did most of trend following's work: a
vol-managed equal-weight hold had net Sharpe 1.24 against 0.79 for
multi-horizon trend. Our ensemble's 0.45–0.47 since 2022 barely beat
buy-and-hold. This test asks whether the Donchian signal adds anything over
holding with the same sizing, and how a plain BTC 200-day filter compares.
See `.mz/research/2026_11_17_research_trading_bot_sota.md`.

## Data

- `data/archive`, TRADING universe (BTC ETH SOL XRP BNB ADA LINK AVAX), daily
  closes and funding exactly as in `2026_11_16_trend_following.md`. HOLDOUT is
  not mirrored, so it is not covered.
- W1, the main window: return days 2022-03-15 to 2026-11-14, as in the
  original trend test.
- W2, the backfill window: return days 2020-12-15 to 2022-03-14, as in
  `2026_11_17_trend_2021_backfill.md`. It is a strong bull market, so an
  always-long rule is expected to look good there; W1 decides.

## Rules

- B1 `vol-hold`: always long every symbol at min(25% / 30-day vol, 2) / 8.
  This is the ensemble with its signal fixed at 1: same vol window, target,
  cap, 20% turnover buffer, commission 0.0005 and daily funding.
- B2 `sma200`: BTCUSDT only, weight 1.0 (unlevered) while the daily close is
  above the mean of the last 200 closes including that day, else 0. Same
  buffer, commission and funding. Its benchmark is BTC buy-and-hold.
- References: H1 (lookbacks 20/40/80) and H2 (lookback 20), run on the archive
  over the same windows. The W2 references are the backfill test's runs.
- Code: `VolManagedHoldSignal`, `SmaFilterSignal`, `DonchianTrendSignal`,
  `TurnoverBuffer` and `TrendPortfolio` as of the commit that adds this file.

## Commands (each run once)

    uv run kavzitrader eval trend --variant vol-hold
    uv run kavzitrader eval trend --variant vol-hold --from 2020-12-15 --to 2022-03-15
    uv run kavzitrader eval trend --variant sma200 --symbols BTCUSDT
    uv run kavzitrader eval trend --variant sma200 --symbols BTCUSDT --from 2020-12-15 --to 2022-03-15
    uv run kavzitrader eval trend
    uv run kavzitrader eval trend --lookbacks 20

All runs land in `results/evals/trials.jsonl`; report the deflated Sharpe of
the best trend-family trial afterwards (`eval trials --family trend`).

## Decision

- Q1, does the Donchian signal add value? On W1: if B1's net Sharpe is at least
  H1's, the signal adds nothing over holding with the same sizing. Then B1 joins
  the lookback-20 forward test as a second paper arm, and the simpler rule is
  kept unless the forward test separates them.
  Otherwise the signal is credited and nothing changes.
- Q2, B2 on W1: PASS if net Sharpe >= 0.5 and above BTC buy-and-hold (the
  original bar). A PASS makes it a candidate arm, not an adopted strategy.
- No parameter in this file may change after the first run, and none of these
  results replaces the forward test.
