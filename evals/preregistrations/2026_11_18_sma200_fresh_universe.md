# 200-day average filter on a never-analysed universe, rules fixed 2026-11-18

Long BTC above its 200-day simple moving average passed on 2022-03-15 to
2026-11-14 (net Sharpe 0.78 against BTC buy-and-hold's 0.54) but failed on the
2021 backfill (0.15 against 1.12). The futures archive has no unused BTC history
long enough to settle it. This test asks the general form of the claim once, on
coins no test has touched: does holding each coin only above its own 200-day
average beat holding them all?

## Data

- Universe: the 115 symbols in `evals/universes/fresh_2022.txt`, the same file
  and rules as `2026_11_18_trend_fresh_universe.md`. Delisted symbols stay in.
- Zero-volume daily bars count as missing: `TrendDataLoader` sets their close
  to NaN, so the symbol holds nothing there. Binance keeps archiving flat
  zero-volume bars after a delisting and during trading pauses, which the fresh
  trend test counted as listed days at 0%. Under this rule 39 symbols stop
  trading before 2026-10-31 (that test counted 14), BTCSTUSDT has no traded
  close in the window, and CTKUSDT, CVCUSDT, LITUSDT and TLMUSDT have 393, 898,
  325 and 293 untraded days inside it. After a pause a symbol needs 200 traded
  closes again before it can hold.
- Daily closes: Binance 1d klines from the archive, from each symbol's first
  archived month (as early as 2019-09). Funding from the archive, summed per
  UTC day.
- Window: return days 2022-03-15 to 2026-10-31 inclusive, as in the fresh trend
  test. 14 symbols reach 200 closes after 2022-03-14, the last on
  2022-07-18; until then they hold nothing.
- The completeness check (continuous daily bars, funding present) and the
  zero-volume check ran before this file was committed. No return on these symbols under this rule was
  computed before then. The lookback-20 trend rule was scored on them on
  2026-11-18 (FAIL, net Sharpe 0.37) on the data before the zero-volume rule;
  its corrected re-run is recorded as an erratum after this file is committed.

## Rule

- `SmaFilterSignal(200)`: weight 1/N while the close is above the mean of the
  last 200 closes (including that day's), else 0. N = 115, unlevered.
- 20% turnover buffer, commission 0.0005 (`paper.commission_rate`), daily
  funding on held weight. A symbol holds nothing on untraded days.
- Code: `TrendDataLoader`, `SmaFilterSignal`, `TurnoverBuffer`,
  `TrendPortfolio`, `WeightBacktest` and `CashRate` as of the commit that adds
  this file.

## Benchmark

Equal-weight buy-and-hold of the symbols traded that day, no costs or funding.
Cash is the 3-month US T-bill rate (`evals/cash/tb3ms_monthly.csv`).

## Command (run once)

    uv run kavzitrader eval trend --variant sma200 \
      --symbols-file evals/universes/fresh_2022.txt --to 2026-11-01 \
      --prereg 2026_11_18_sma200_fresh_universe.md \
      --out results/evals/sma200_fresh.md

## Decision

- PASS: net Sharpe >= 0.5 AND above the benchmark's AND Sharpe over cash > 0.
  Otherwise FAIL. The cash condition is new: since 2026-11-18 every report
  shows it, and a rule that does not beat T-bills is not worth running.
- PASS: the filter works beyond BTC. A BTC-only arm still needs its own
  forward test before paper; this result is evidence for it, not a substitute.
- FAIL: the BTC result is likely a single-asset accident. Add the 200-day
  filter to the closed lines in `evals/README.md`.
- Known before running: buy-and-hold of these coins lost 22% a year over this
  window in the fresh trend test, which counted dead coins' flat days as 0%.
  The corrected figure is not computed before this test runs. Beating the
  benchmark is likely easy, so the absolute and cash conditions do the work.
- No parameter in this file may change after the first run.
