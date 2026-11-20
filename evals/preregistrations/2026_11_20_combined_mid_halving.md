# Mid exit and vol-spike halving scored together, rules fixed 2026-11-20

The mid-channel exit and the vol-spike halving each passed alone on 2026-11-19
and went into the paper rule on 2026-11-20 without being scored as a pair. This
test scores the 2x2 once: does the mid exit's gain survive with halving on, and
does halving's cost stay small under the mid exit.

## Data

The 8 trading symbols only: halving needs 1m klines, which the 115 fresh coins
do not have, so the fresh universe cannot score it. Return days 2022-03-15 to
2026-10-31, daily bars, commission 0.0005 (`paper.commission_rate`), daily
funding, 20% turnover buffer: the same data, window and costs as
`2026_11_19_trend_exit_speed_ablation.md` and `2026_11_19_crash_replay.md`.

## Arms (one run, four series)

- Base: Donchian long/flat, lookback 20, vol window 30, 25% vol target, 2x cap.
- `mid`: the base with the exit below the prior 20-day midpoint (`MidExitTrendSignal`).
- `halving`: the base plus `VolSpikeHalving` (99th percentile of 2160 hours, at
  least 720, first spike before 23:00 UTC halves the coin until the rebalance,
  both legs pay the commission).
- `mid+halving`: the paper rule. Halving is priced on the mid exit's own held
  weights, not the base's.
- Code: `CombinedArmsScorer`, `CombinedArmsVerdict`, `PairedSharpeTest` as of the
  commit that adds this file. Paired stationary block bootstrap, 5000 resamples,
  mean block 20 days, seed 20261119, 90% interval.

## Reproduction check

On this data `base`, `mid` and `halving` were already scored: Sharpe 0.640,
0.905 and 0.624. If any differs by more than 0.002, code or data changed since
2026-11-19: the run is VOID, no decision is taken, and the cause is found
before a re-run.

## Metrics

Primary, two Sharpe differences:

- Mid gain with halving on = Sharpe(`mid+halving`) - Sharpe(`halving`). Alone it
  was +0.265 here.
- Halving cost under the mid exit = Sharpe(`mid`) - Sharpe(`mid+halving`). Under
  the base it was +0.016.

Secondary, reported and not decisive: net Sharpe, Sharpe over cash, annual
return, volatility and max drawdown per arm; Sharpe by year; symbol-days with a
spike while held under each exit; the 90% intervals of all differences (the
trading-8 intervals are wide and are not a gate, as on 2026-11-19);
`mid+halving` minus base.

## Decisions (each applied independently)

- Mid exit: KEEP if the mid gain with halving on is >= +0.13 (half its separate
  gain). Otherwise DROP: set `exit_rule` back to `low`.
- Halving: KEEP if the cost under the mid exit is <= 0.05, the bar it was adopted
  under. A negative cost is a benefit and passes. Otherwise DROP: turn
  `vol_spike` off.
- Both KEEP: the paper rule stays `mid+halving`. One DROP: the paper rule becomes
  the other change alone. Both DROP: back to the low exit without halving.
- The 2025-10-10 replay is not re-scored: it measures the disaster stop and the
  halving day return, not the exit rule.
- This is a check on a combination, not a new adoption test. A KEEP does not add
  evidence for either change, and mid exit's narrow fresh-universe pass still
  stands undeflated.
- No parameter, threshold or arm in this file may change after the run, and no
  further arms are added to rescue a DROP.

## Command (run once)

    uv run kavzitrader eval combined-mid-halving \
      --prereg 2026_11_20_combined_mid_halving.md \
      --out results/evals/combined_mid_halving.md

The run registers the `mid+halving` series as one more `trend` trial.
