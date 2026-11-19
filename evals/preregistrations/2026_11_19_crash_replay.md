# Replay of 10 October 2025 and a vol-spike halving rule, rules fixed 2026-11-19

On the evening of 2025-10-10 (UTC) many perpetuals' last prices wicked far
below their mark prices for minutes. The paper rule's 30% disaster stop
triggers on the last price, Binance's default for STOP_MARKET. This
test replays the day minute by minute and prices a rule that halves a coin
after a 1-hour volatility spike
(`.mz/research/2026_11_19_research_trade_algos.md`, test 5).

## Data

- The 8 trading symbols. 1m klines and 1m mark-price klines from the archive:
  1440 bars each on 2025-10-10 and every month 2021-12 to 2026-10 present
  (checked before this file was committed, row counts only).
- Daily closes and funding as in the other 2026-11-19 tests.

## Replay (2025-10-10)

- Book: the weights the paper rule held into 2025-10-10 (set at the 2025-10-09
  close) over the 2022-03-15 to 2026-10-31 backtest, unknown when this file
  was written.
- Stop: 30% below the 2025-10-09 close, as the executor places it at the
  rebalance.
- Variants: no stop; as live (last-price trigger, filled at the minute's low or
  the stop, whichever is lower); mark-price trigger (same fill); as live plus
  halving; last-price trigger filled at the stop (the best case).
- Reported per variant: the day's book return, the worst minute's mark-to-low
  return and its time, and each stop's minute and fill.
- Not modelled: ADL, the spread, and the margin asset. Klines carry no spread,
  so a spread trigger is dropped.

## Halving rule

- Hourly variance: the sum of squared 1m log returns in the hour. A spike is
  an hour above the 99th percentile of the previous 2160 hours (at least 720).
- The first spike of a UTC day before 23:00 halves that coin at the hour's last
  close until the next daily rebalance. Both legs pay the commission.
- Full-window cost: the base daily net returns plus each spike day's change,
  return days 2022-03-15 to 2026-10-31, compared by the paired bootstrap.

## Command (run once)

    uv run kavzitrader eval crash-replay --day 2025-10-10 \
      --prereg 2026_11_19_crash_replay.md \
      --out results/evals/crash_replay_2025_10_10.md

## Decisions

- Halving: ADOPT if its replay day return is above the as-live variant's AND
  it costs at most 0.05 Sharpe over the full window. Otherwise REJECT.
- Stop trigger: switch the disaster stop to `workingType=MARK_PRICE` if any
  last-price stop fired that the mark-price stop did not AND filled below that
  coin's close-to-close return for the day. Otherwise keep the last price.
- If the rule held nothing into the day, every variant returns 0, halving
  cannot beat as-live and is REJECTED, and the trigger stays on the last price.
- No parameter in this file may change after the first run.
