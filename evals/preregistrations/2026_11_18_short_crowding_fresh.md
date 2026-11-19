# SHORT crowding signals on never-analysed coins, rules fixed 2026-11-18

Two SHORT flags passed `2026_11_16_positioning_metrics.md` on TRADING and
HOLDOUT, but not STRONG: their 95% lower bounds sat below the fee. They are the
only signals left with a preregistered pass. This test scores them once on
coins that test never saw, with the same definitions, data source and bracket.

## Data

- Universe: the 101 symbols in `evals/universes/fresh_2022_survivors.txt`. The
  REST API serves no candles for the 14 symbols of the fresh universe that left
  the archive, so they cannot be scored. "Still archived" did not mean "still
  traded": Binance keeps publishing flat zero-volume bars after a delisting, and
  26 of the 101 stopped trading between 2022-06 and 2026-08.
- Zero-volume bars count as missing: `CandleCache.load_traded` drops them, so a
  delisted symbol ends at its last traded bar. RAYUSDT and SCUSDT have no
  traded bar in the window; 24 others end inside it (DGB 2024-04-01 to ICX and
  STORJ 2026-08-26). CTK, CVC and LIT start late (2025-04-30, 2025-05-16,
  2025-12-23) and hold no rank until they have 1000 bars.
- 4h candles, funding and the 5-minute metrics archive in `data/eval_cache`,
  filled by `eval refresh-cache --interval 4h --months 66 --metrics`, finished
  2026-11-19.
- Window: bars closing 2023-06-18 to 2026-11-14, not 2022-01-01 as in the
  original test. Both ratios are empty on most 2022 archive rows, and the signal
  carries the last ratio forward with no age limit, so from 2022-01-01 26% of
  bars would read a ratio over 24h old. The ranking window is 1000 bars (about 167 days),
  so 2023-06-18 is the first day whose whole ranking window lies in 2023. In
  this window: 99 symbols, 649,492 traded 4h bars, 33 of them with a ratio over
  24h old (at most 7 per symbol), and none in the ranking warm-up.
- The completeness, zero-volume and ratio-age checks ran before this file was
  committed. No signal on these symbols was scored before then.

## Signals and test (unchanged from 2026-11-16)

- `ls_crowding` SHORT: global long/short account ratio, percentile-ranked
  within the trailing history window, fires at rank >= 2/3.
- `smart_vs_crowd` SHORT: log(top-trader position ratio) - log(global account
  ratio), ranked the same way, fires at rank <= 1/3.
- Interval 4h, stride 1, bracket `1.5:3:12` (the only one that counts).
- Code: the live definitions and `eval signals` as of the commit that adds
  this file. The only change from 2026-11-16 is that `eval signals` now drops
  zero-volume bars.

## Command (run once)

    uv run kavzitrader eval signals --interval 4h --stride 1 --metrics \
      --bracket 1.5:3:12 --from 2023-06-18 --to 2026-11-15 \
      --symbols-file evals/universes/fresh_2022_survivors.txt \
      --out results/evals/short_crowding_fresh.md

## Decision, per signal (2 tests; every other row of the report is ignored)

- PASS: fired mean R minus fee > 0 AND lift > 0.
- STRONG PASS: also the lower 95% bound of fired mean R > fee.
- Anything else is FAIL.
- STRONG PASS: the signal earns a paper-trading preregistration of its own
  (sizing, exits, a forward window). It is not traded before that exists.
- PASS: the original result replicates, but the edge is not distinguishable
  from the fee. Record it; no paper arm.
- FAIL: add the signal to the closed lines in `evals/README.md`.
- Known before running: the original fired lifts were +0.057 to +0.083 R
  against a fee of about 0.035 R. These coins are thinner, so a real edge may
  look larger and still not survive slippage, which the bracket does not model.
- The original test ran from 2022-01-01 with the same stale ratios in 2022, so
  part of its pass may come from them. This test cannot tell; it only checks
  whether the edge exists where the data is clean.
- No definition, threshold or window may change after the first run.
