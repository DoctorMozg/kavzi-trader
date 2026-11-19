# Better volatility forecasts for trend sizing, rules fixed 2026-11-19

The trend rule sizes each coin by its trailing 30-day volatility, and vol
targeting supplies most of a trend book's Sharpe. This test asks whether a
better 7-day forecast of realized variance improves the book
(`.mz/research/2026_11_19_research_trade_algos.md`, test 2).

## Data

- The 8 trading symbols, daily closes from the archive, return days 2022-03-15
  to 2026-10-31. Variance targets need 7 later days, so the last forecast is
  made at the close of 2026-10-24.
- Deribit DVOL (30-day implied vol index, daily close) for BTC and ETH, from
  `eval dvol-download --to 2026-11-01`: 2049 days each, 2021-03-24 to
  2026-11-01, no gaps or duplicates (checked before this file was committed).
- Chronos-2: `amazon/chronos-2` at Hugging Face revision
  `29ec3766d36d6f73f0696f85560a422f50e8498c`, downloaded and smoke-tested on a
  synthetic sine series only.

## Stage A: forecast accuracy

- Target: realized variance of the next 7 daily log returns, annualised.
- Baseline `rolling-30d`: the rule's own trailing 30-day variance.
- Candidates, each fitted only on data whose targets ended before the refit
  day, refitted at each month start:
  - `har`: pooled OLS of log forward variance on log 1-, 7- and 30-day
    variance; forecast exp(fit + residual variance / 2).
  - `har-dvol`: `har` plus log DVOL variance; BTC and ETH only.
  - `lgbm`: LightGBM (native API, fixed parameters in `LGBM_PARAMS`, 300
    rounds, seed 20261119) on the `har` features plus 3- and 14-day variance
    and the day's return.
  - `chronos-2`: zero-shot median of the 7-day-ahead log variance from up to
    512 days of history; no fitting.
- Loss: QLIKE. Test: Diebold-Mariano on the daily mean loss difference,
  Newey-West lag 7, one-sided.
- Each candidate is scored against `rolling-30d`; `har-dvol` is also scored
  against `har`, on BTC and ETH only.

## Stage B: trading

- Winner: among `har`, `lgbm` and `chronos-2`, the lowest QLIKE among those
  that beat `rolling-30d` at p < 0.05. None: stage B does not run.
- Arm: the paper rule with the winner's forecast in place of the trailing
  variance (weight = signal x min(0.25 / sqrt(forecast), 2) / 8); otherwise
  unchanged. Base: the paper rule.
- Paired block bootstrap as in `2026_11_19_trend_exit_speed_ablation.md`.

## Command (run once)

    uv run kavzitrader eval vol-forecast \
      --chronos-revision 29ec3766d36d6f73f0696f85560a422f50e8498c \
      --prereg 2026_11_19_vol_forecast.md \
      --out results/evals/vol_forecast_trading.md

## Decision

- ADOPT: stage B ran and the 90% interval's lower bound of the Sharpe
  difference is > 0. ADOPT earns a forward paper test of its own.
- Stage A without stage B, or stage B with the bound <= 0: REJECT for trading.
  A stage A winner is still recorded as the better forecaster.
- `har-dvol` vs `har` is informational: DVOL covers 2 of 8 coins, so it cannot
  change the book on its own.
- 4 forecasters are scored, so a p just under 0.05 is weak; no correction is
  applied, which favours the candidates.
- No parameter in this file may change after the first run.
