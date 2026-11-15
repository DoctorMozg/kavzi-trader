# Forward test: SHORT taker_flow+funding_favorable, rules fixed 2026-11-16

The 2026-11-15 combination test found this rule after looking at its results
(train +0.055 R, holdout +0.079 R, fee ~0.035 R, lower bounds below the fee).
This file fixes the test before any of its data exists. The commit that adds
it is the timestamp.

## Rule

- Side SHORT only. Fires when both flags fire on the same 4h bar:
  - `taker_flow` SHORT: taker-buy share of volume over the last 4 bars ranks in
    the bottom third of the trailing 1000-bar window
    (`kavzi_trader/evals/candidate_signals.py`).
  - `funding_favorable` SHORT: the live funding z-score (latest settlement over
    the last 100) is >= 0 (`kavzi_trader/spine/filters/confluence.py`).
- Definitions as of commit `c0cac1f`. A later change to either flag, the
  bracket labeller or `history_candles` voids this test.

## Data

- Interval 4h, stride 1, bracket `1.5:3:12` (SL 1.5 ATR, TP 3 ATR, 48h).
  No other bracket counts.
- 16 symbols: BTC ETH SOL XRP BNB ADA LINK AVAX DOGE LTC DOT BCH ATOM TRX ETC
  FIL (USDT perps). None of their bars after the cache end (2026-11-15 00:00
  UTC) has been looked at.
- Window: bars closing from 2026-11-15 (inclusive) to 2027-11-15 (exclusive).
- Fee: taker round trip from `paper.commission_rate` (0.0005), in R, as the
  report prints it.

## Command (run once, on or after 2027-11-17 so 48h outcomes are complete)

    uv run kavzitrader eval refresh-cache --interval 4h --symbols <16 symbols>
    uv run kavzitrader eval signals --interval 4h --stride 1 --candidates \
        --funding --bracket 1.5:3:12 --combo taker_flow+funding_favorable \
        --symbols <16 symbols> --from 2026-11-15 --to 2027-11-15

## Decision

- PASS: fired mean R minus fee > 0 AND lift > 0.
- STRONG PASS: lower 95% bound of fired mean R > fee.
- Anything else is FAIL, and the rule is dropped.
- No early looks. The scheduled refresh only grows the cache; nobody scores
  the window before 2027-11-17.

## Power, stated up front

About 500 fired bars a month across 16 symbols. From the holdout's spread, 12
months gives a 95% interval of roughly +/-0.10 R on fired mean R, while the
effect we hope for is about +0.04 R above the fee. A PASS therefore means "not
refuted", not "proven". Only a STRONG PASS justifies a paid eval of the rule.
