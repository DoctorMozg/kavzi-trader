# Forward test: trend following, lookback 20 only, rules fixed 2026-11-16

The pre-registered ensemble (lookbacks 20/40/80) failed: net Sharpe 0.446
TRADING and 0.496 HOLDOUT, against a 0.5 bar. Lookback 20 alone scored 0.64
and 0.65 in an exploratory run, chosen after looking at results, so it gets
its own test on data that doesn't exist yet. The live trend plugin runs this
rule on paper only until the test is scored.

## Rule

`2026_11_16_trend_following.md` with one change: lookbacks = {20}. Everything
else stays as written there: long/flat, vol window 30, 25% vol target, 2x
cap, N = 8, the 20% turnover buffer, commission 0.0005 and daily funding.
The code is `DonchianTrendSignal` and `TurnoverBuffer` as of the commit that
adds this file.

## Data

- Universes: TRADING = BTC ETH SOL XRP BNB ADA LINK AVAX; HOLDOUT = DOGE LTC DOT
  BCH ATOM TRX ETC FIL. Each is scored on its own.
- Return days from 2026-11-15 to 2027-11-14 inclusive. The cache ended on
  2026-11-14 when this file was written. The weekly refresh fills both
  universes at 4h.

## Command (run once, on or after 2027-11-16)

    uv run kavzitrader eval trend --lookbacks 20 --from 2026-11-15 \
        --to 2027-11-15 --symbols <universe>

## Decision

- PASS: net Sharpe >= 0.5 on BOTH universes AND above the benchmark's on
  BOTH (the original bar).
- Otherwise FAIL, and the trend plugin is removed from paper trading.
- No early looks at the score. The paper plugin's own fills are checked only
  for execution parity with the backtest, not for performance.
