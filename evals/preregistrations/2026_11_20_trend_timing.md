# Trend rule off daily bars, rules fixed 2026-11-20

The paper rule decides once a day at the 00:00 UTC close. This test asks
whether deciding faster helps, in two ways and at three speeds each, scored
once against the daily rule. Nothing in the paper rule changes because of it:
an ADOPT candidate only earns the owner's decision.

## Data

- Universes and window as in `2026_11_19_trend_exit_speed_ablation.md`: primary
  the 115 fresh symbols (`evals/universes/fresh_2022.txt`), secondary the 8
  trading symbols, return days 2022-03-15 to 2026-10-31, commission 0.0005
  (`paper.commission_rate`), 20% turnover buffer.
- New dataset `klines_1h`: Binance's own 1h USD-M klines
  (`data/archive/klines/<SYMBOL>/1h/YYYY-MM.parquet`), mirrored for all 123
  symbols from 2020-01 to 2026-10. The 4h, 6h and 12h bars of every symbol,
  both universes, are built from it (`IntradayDataLoader`): a bar closes at its
  last hour's close and counts only if all its hours exist.
- The daily path is unchanged: daily closes, the zero-volume rule and daily
  funding come from `TrendDataLoader` as on 2026-11-19 (1d bars for the fresh
  coins, 1m rolled to 4h for the trading 8). The base is scored from them, so it
  does not depend on the 1h data. The last bar of each UTC day in every arm
  carries that day's close from the daily data, and a day the daily path calls
  untraded has no bars.
- Hours missing inside a traded day carry the previous close (zero return for
  that hour). The report counts them.
- Funding is the daily sum of settlements, as in the base. A day's funding is
  paid on the time-weighted average held weight of its bars, so a day with one
  weight pays exactly what the base pays.

## Rule shared by all arms

- Long/flat mid-exit Donchian, lookback 20 (`MidExitTrendSignal`): enter on a
  price above the max of the previous 20 closes, exit on a price below the
  midpoint of their max and min, otherwise keep the state.
- Sizing as the base: `min(0.25 / vol, 2)` times the state, over N symbols. `vol`
  is the std of the daily log returns of the 30 most recent completed days
  times sqrt(365). At the 00:00 check this is the base's number; at an
  intraday check it is the previous day's, the latest known.
- Turnover buffer 0.2 applied at every check, starting flat on the first scored
  return day, as in the base.
- Weights set at a check are held to the next check. A weight is notional per
  unit of the day-start price, so a day with no weight change returns exactly
  `weight x (close / previous close - 1)` whatever the number of bars.
  Commission is `0.0005 x |weight change|` at each check, charged on the
  interval after it.
- Vol-spike halving is excluded from all arms, base included: the fresh coins
  have no 1m bars to trigger it. The base here is therefore the paper rule
  without halving, the one scored on 2026-11-19 (fresh 0.688, trading 0.905).
- Returns are summed to UTC daily net returns, so every arm is compared day by
  day with the base.

## Arms (6 trials)

- A, shorter bars, same rule in bars: the mid-exit Donchian run on 12h, 6h and 4h
  bars with lookback 20 bars (10, 5 and 3.3 days). Signal and rebalance at each
  bar close. Arms `A-12h`, `A-6h`, `A-4h`.
- B, same 20-day channel, checked more often: entry level is the max and exit
  level the midpoint of the previous 20 completed daily closes, exactly the base's
  levels, compared with the price at every 12h, 6h or 4h bar close (UTC-aligned:
  00 and 12; 00, 06, 12, 18; 00, 04, ... 20), trading at that close. The bars
  closing during UTC day x face the levels x's own daily close faces, so no
  level uses a close that is not yet complete. Arms `B-12h`, `B-6h`, `B-4h`.
- The 00:00 daily check is the base itself. Code: `TimingBacktest`,
  `TimingStates`, `TimingScorer`, `TimingVerdict`, `PairedSharpeTest` as of the
  commit that adds this file.

## Reproduction and integrity checks

- The base must score Sharpe 0.688 on the fresh 115 and 0.905 on the trading 8,
  each within 0.002. Otherwise that universe's run is VOID: no decision, and the
  cause is found before a re-run.
- Of the listed symbol-days, at most 0.1% may have a 1h-derived day close that
  differs from the daily bar by more than 1e-6 (relative). Otherwise VOID: the
  1h archive does not match the daily one.

## Test

Paired comparison of daily net returns, arm minus base: stationary block
bootstrap, 5000 resamples, mean block 20 days, seed 20261119 (the same resample
days for both intervals).

Six arms give six chances of a lucky pass. The decision interval is
Bonferroni-adjusted: two-sided, per arm 1 - 0.10 / 6 = 98.33%. The plain 90%
interval is reported beside it and decides nothing.

Reported per arm and universe, not decisive: net Sharpe, Sharpe over cash, annual
return, max drawdown, trades per year (weight changes over all symbols), turnover
(x NAV per year), cost drag (return points per year), Sharpe by year.

## Decision, per arm

- ADOPT candidate: the adjusted interval's lower bound is > 0 on the fresh 115
  AND the Sharpe difference is >= 0 on the trading 8. Otherwise REJECT.
- A candidate changes nothing in the paper rule. The owner decides, and a
  candidate that is also faster to trade, with more trades and cost drag, is
  weighed against that; this file sets no bar for it.
- No parameter, arm or threshold in this file may change after the run, and no
  further arms are added to rescue a REJECT.
- The six runs register six `trend` trials per universe (12 in all), which count
  against the family's deflated Sharpe.

## Commands (each run once)

The 1h mirror first, about 8,400 monthly files and 330 MB. It is a download and
needs the owner's go-ahead.

    uv run kavzitrader eval archive --dataset klines_1h \
      --symbols "$(sed 's/#.*//; s/[[:space:]]//g; /^$/d' evals/universes/fresh_2022.txt | paste -sd,),BTCUSDT,ETHUSDT,SOLUSDT,XRPUSDT,BNBUSDT,ADAUSDT,LINKUSDT,AVAXUSDT"

Then one run per universe, all six arms inside:

    uv run kavzitrader eval trend-timing --universe fresh \
      --prereg 2026_11_20_trend_timing.md \
      --out results/evals/trend_timing_fresh.md
    uv run kavzitrader eval trend-timing --universe trading \
      --prereg 2026_11_20_trend_timing.md \
      --out results/evals/trend_timing_trading.md
