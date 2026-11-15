# Positioning and 5-year OI signals, rules fixed 2026-11-16 before any code or result

Binance's free data.binance.vision `metrics` archive
(`data/futures/um/daily/metrics/<SYM>/<SYM>-metrics-YYYY-MM-DD.zip`, 5-minute
rows since about 2020-09) carries open interest and long/short ratios. Our
earlier OI tests had only 27 days of history.

## Data

- Download `metrics` for the 16 cached symbols over the 4h cache range.
- Before scoring, check which column is the global account ratio and which is
  the top-trader position ratio by comparing them with the 30-day REST
  endpoints (`/futures/data/globalLongShortAccountRatio`,
  `/futures/data/topLongShortPositionRatio`). If they can't be matched, the
  long/short signals are not scored.
- Each 4h bar uses the latest metrics row at or before its close.

## Signals (side flags, scored with `eval signals`)

- `oi_supports_direction` and `oi_funding_divergence`: the live definitions
  through the live `OrderFlowCalculator`, with metrics OI in place of the
  `openInterestHist` cache.
- `ls_crowding`: global long/short account ratio, percentile-ranked within
  the trailing 1000 bars (as `taker_flow`). Rank <= 1/3 fires LONG (the crowd
  is short), rank >= 2/3 fires SHORT.
- `smart_vs_crowd`: log(top-trader position ratio) - log(global account
  ratio), ranked the same way. Rank >= 2/3 fires LONG, <= 1/3 fires SHORT.

## Test

- Interval 4h, stride 1, bracket `1.5:3:12` (the only one that counts), bars
  closing from 2022-01-01 to 2026-11-15.
- Two symbol sets scored separately: TRADING = BTC ETH SOL XRP BNB ADA LINK
  AVAX; HOLDOUT = DOGE LTC DOT BCH ATOM TRX ETC FIL.

## Decision, per signal and side (8 tests)

- PASS: on BOTH sets, fired mean R minus fee > 0 AND lift > 0.
- STRONG PASS: also the lower 95% bound of fired mean R > fee on both sets.
- Anything else is FAIL. No definition, threshold or window may change after
  the first run.
