# B-6h on the trend holdout, rules fixed 2026-11-21

`2026_11_20_trend_timing.md` scored approach B (the daily 20-day channel
checked at every intraday bar close) better than the daily rule on both
universes at every speed, but no arm cleared its Bonferroni bar: all six were
REJECT. This test confirms one B arm, once, on coins it has never been scored
on. The six arms' data cannot be re-scored to rescue them.

## Arm (1 trial)

- `B-6h`, as defined in `2026_11_20_trend_timing.md`: entry and mid exit levels
  from the previous 20 completed daily closes, compared with the price at every
  6h bar close (00, 06, 12, 18 UTC), trading at that close. Chosen before any
  holdout data was downloaded: it had the highest Sharpe of the B arms on both
  universes (fresh 0.848, trading 1.219).
- Base: the daily paper rule without halving (mid-exit Donchian long/flat,
  lookback 20), sizing, buffer, costs and funding exactly as in the timing test.
- Code: `TimingBacktest`, `TimingScorer`, `TimingVerdict.holdout_outcome`,
  `PairedSharpeTest` as of the commit that adds this file.

## Data

- The trend holdout of `2026_11_16_trend_following.md`: DOGE LTC DOT BCH ATOM
  TRX ETC FIL (USDT perps). The daily rule was scored there on 2026-11-16 (low
  exit, lookbacks 20/40/80); no timing arm and no mid exit ever was.
- Return days 2022-03-15 to 2026-10-31, as in the timing test.
- Mirrored from data.binance.vision into the archive: `klines_1d` (daily path),
  `klines_1h` (6h bars) and `funding`. Vol-spike halving is excluded: these coins
  have no 1m bars.
- No reproduction check: the holdout has no earlier mid-exit score. The bar
  integrity check of the timing test applies unchanged (at most 0.1% of day
  closes from the 1h bars may differ from the daily bars, else VOID).

## Test

Paired comparison of daily net returns, B-6h minus base: stationary block
bootstrap, 5000 resamples, mean block 20 days, seed 20261119, 90% interval. One
arm, so no Bonferroni split.

## Decision

- CONFIRM: the 90% lower bound is > 0. B-6h becomes a candidate for the paper
  rule; the owner decides, and the paper trader needs a 6-hourly check before it
  can run it.
- INCONCLUSIVE: the difference is > 0 but the interval reaches 0. Eight coins
  are a weak test; B-6h then needs a forward test on data after 2026-10-31
  before any change.
- FAIL: the difference is <= 0. Approach B closes.
- Reported, not decisive: Sharpe, return, drawdown, trades per year, turnover,
  cost drag and Sharpe by year for both.
- Nothing in this file may change after the download, and no other arm or
  universe is added afterwards.

## Commands (each run once)

    uv run kavzitrader eval archive --dataset klines_1d --dataset klines_1h \
      --dataset funding \
      --symbols DOGEUSDT,LTCUSDT,DOTUSDT,BCHUSDT,ATOMUSDT,TRXUSDT,ETCUSDT,FILUSDT
    uv run kavzitrader eval trend-timing --universe holdout \
      --prereg 2026_11_21_trend_timing_holdout.md \
      --out results/evals/trend_timing_holdout.md
