# Trend following on unused 2020–2022 history, rules fixed 2026-11-17

The ensemble (lookbacks 20/40/80) failed its pre-registered test on return days
2022-03-15 to 2026-11-14. Lookback 20 alone was picked afterwards and is frozen
as a forward test (`2026_11_16_trend_lookback20_forward.md`). The Binance
archive mirror now reaches back to 2020-01, so both rules get one score on
history no test has used: the REST cache started in late 2021, and no trend
rule has been run on any day before 2022-03-15.

## Data

- `data/archive` (`eval archive`), 1m klines rolled into 4h candles, then into
  UTC days as in `2026_11_16_trend_following.md`. Funding from the archive,
  summed per UTC day.
- Universe: TRADING only (BTC ETH SOL XRP BNB ADA LINK AVAX). HOLDOUT is not
  mirrored, so this test does not cover it.
- Window: return days 2020-12-15 to 2022-03-14 inclusive. AVAX's first full
  futures day is 2020-09-24, so 2020-12-15 is the first day on which every
  symbol has 80 days of closes behind it.

## Rules

- H1: the ensemble, exactly as in `2026_11_16_trend_following.md` (lookbacks
  {20, 40, 80}, long/flat, vol window 30, 25% vol target, 2x cap, N = 8, 20%
  turnover buffer, commission 0.0005, daily funding).
- H2: the same with lookbacks = {20}, as in the forward test.
- The code is `DonchianTrendSignal`, `TurnoverBuffer` and `TrendPortfolio` as
  of the commit that adds this file.

## Commands (each run once)

    uv run kavzitrader eval trend --from 2020-12-15 --to 2022-03-15
    uv run kavzitrader eval trend --lookbacks 20 --from 2020-12-15 --to 2022-03-15

## Decision, per rule

- PASS: net Sharpe >= 0.5 AND above the equal-weight buy-and-hold benchmark's
  (the original bar).
- Otherwise FAIL.
- Known before running: 2021 was a strong bull market for these coins, so
  buy-and-hold will be hard to beat on Sharpe, and a PASS on a window this
  short and one-sided is weaker evidence than one over mixed regimes.
- This test does not replace the forward test. The lookback-20 forward test
  still decides whether the paper plugin stays.
- No parameter in this file may change after the first run.
