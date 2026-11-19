# ls_crowding as a market-neutral cross-section, rules fixed 2026-11-19

`ls_crowding` SHORT got a STRONG PASS on 101 fresh coins
(`2026_11_18_short_crowding_fresh.md`). Most of that edge may be market drift:
shorts fired mostly while alts fell. This test removes the drift before any
paper preregistration: a dollar-neutral book that shorts the most crowded third
and longs the least crowded third, with its return regressed on BTC
(`.mz/research/2026_11_19_research_trade_algos.md`, test 7).

## Data

- Same symbols, source and window as the 2026-11-18 test: the 101 symbols of
  `evals/universes/fresh_2022_survivors.txt`; 4h candles (zero-volume bars
  dropped), funding and 5-minute metrics from `data/eval_cache`; return days
  2023-06-18 to 2026-11-14.
- This reuses data the 2026-11-18 test already scored, so it is a diagnostic
  of that pass, not new out-of-sample evidence. A PASS here still needs the
  forward paper test.
- Checked before this file was committed (row counts only): every symbol has
  4h candles; 3 have under 90% of the window's bars (late listing or
  delisting); 27 have under 90% of the metrics rows; RAYUSDT and SCUSDT have
  no ratio in the window and never enter the book.
- Market: BTCUSDT from the same cache.

## Rule

- Rank: each coin's global long/short account ratio, percentile-ranked within
  its own last 1000 known 4h values (as `ls_crowding`), read at each day's last
  4h close (00:00 UTC). It reads the metrics row at least 5 minutes older than
  the close, so a row stamped at its interval's end is never seen early.
  A ratio over a day old gives no rank.
- Book: the first at the 2023-06-18 close, then every 7 days. The coins with a
  rank and a close are sorted; the top third (most crowded) is short and the
  bottom third long, equal weight, 0.5 gross per leg. Fewer than 3 names a leg:
  flat. Weights are held until the next rebalance, with no buffer.
- Costs: commission 0.0005 x |weight traded|, and each day's actual funding
  (a short receives positive funding).
- Code: `CrowdingXsLoader`, `CrowdingXsSignal`, `MarketAlpha`, `WeightBacktest`
  and `eval crowding-xs` as of the commit that adds this file.

## Command (run once)

    uv run kavzitrader eval crowding-xs \
      --symbols-file evals/universes/fresh_2022_survivors.txt \
      --prereg 2026_11_19_ls_crowding_market_neutral.md \
      --out results/evals/crowding_xs_fresh.md

## Decision

- Daily net return = alpha + beta x BTC daily return + error, OLS with
  Newey-West standard errors (lag 5).
- PASS: alpha > 0 AND its t-statistic >= 2. PASS: the market-neutral version
  goes to a paper-trading preregistration of its own.
- FAIL: `ls_crowding` closes. Add it to the closed lines in `evals/README.md`;
  the directional STRONG PASS is recorded as drift.
- Known before running: 26 of the 101 survivors stopped trading inside or
  before the window; a dead coin leaves the book at its last traded bar.
- No parameter in this file may change after the first run.
