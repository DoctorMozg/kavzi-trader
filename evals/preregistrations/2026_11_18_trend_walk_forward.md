# Walk-forward lookback choice, rules fixed 2026-11-18

Lookback 20 was chosen after seeing that it scored best on 2022-2026. This test
asks whether the choice survives without hindsight. Each year trades the
lookback that scored best on the years before it only, and the stitched result
is scored once.

## Data

- Universe: TRADING (BTC ETH SOL XRP BNB ADA LINK AVAX).
- Daily closes from `data/archive`, as in `2026_11_17_trend_2021_backfill.md`
  (1m klines rolled into 4h candles, then into UTC days). Funding from the
  archive, summed per UTC day.
- Training starts 2020-12-15, the first day every symbol has 80 days of closes.
  Lookback 120 needs 120 days of closes, so for SOL and AVAX it holds nothing
  until mid to late January 2021.

## Procedure

- Candidates: single-lookback Donchian long/flat rules with lookback in
  {10, 20, 30, 40, 60, 80, 120}, each with the paper sizing (vol window 30,
  25% vol target, 2x cap, N = 8), 20% turnover buffer, commission 0.0005 and
  daily funding.
- Test periods: calendar years 2022, 2023, 2024, 2025, and 2026 up to
  2026-10-31.
- For each test period: score every candidate's net Sharpe on the return days
  from 2020-12-15 to the day before the period (expanding window). The highest
  wins; a tie goes to the shorter lookback.
- The chosen rules are stitched into one target-weight series. The turnover
  buffer runs over it continuously, so a year boundary does not force a trade.
- Code: `WalkForward`, `ScheduledSignal` and `WeightBacktest` as of the commit
  that adds this file.

## Benchmark

Equal-weight buy-and-hold of the same 8 symbols over the same days, no costs
or funding.

## Command (run once)

    uv run kavzitrader eval trend-walkforward \
      --prereg 2026_11_18_trend_walk_forward.md \
      --out results/evals/walkforward_trading.md

## Decision

- PASS: net Sharpe of the stitched 2022-01-01 to 2026-10-31 series >= 0.5 AND
  above the benchmark's. Otherwise FAIL.
- PASS: picking the lookback from past data works, so the paper rule's choice
  was not pure hindsight.
- FAIL: the lookback-20 result depends on hindsight. The forward test is the
  only clean evidence left, and the backtest Sharpe of 0.64 should not be
  quoted as the rule's expected performance.
- Known before running: lookbacks 20, 40 and 80 were all scored on 2022-2026,
  and lookback 20 did best overall. Each yearly choice can only use the years
  before it, so that knowledge cannot enter the choices, but the candidate grid
  was written knowing it. The 2022 choice rests on 2021 alone, a bull market.
  2022-01-01 to 2022-03-14 and the 2021 training days were already scored in
  the 2021 backfill test.
- Exploratory only, not part of the decision: the report also scores fixed
  lookback 20 over the same days, to show the size of the hindsight gap.
- No parameter in this file may change after the first run.
