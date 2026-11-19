# Exit and speed ablations of the trend rule, rules fixed 2026-11-19

Two changes with weak, in-sample support (Zarattini et al. 2025; the
AdaptiveTrend ablation) are scored once each against the paper rule
(`.mz/research/2026_11_19_research_trade_algos.md`, test 4).

## Data

As in `2026_11_19_funding_crowding_overlay.md`: primary the 115 fresh symbols,
secondary the 8 trading symbols, return days 2022-03-15 to 2026-10-31.

## Arms (2 trials)

- Base: the paper rule (Donchian long/flat lookback 20, vol window 30, 25% vol
  target, 2x cap, 20% turnover buffer, commission 0.0005, daily funding).
- `mid-exit`: enter as the base does (close above the prior 20-day high); exit
  when the close falls below the midpoint of the prior 20-day high and low,
  instead of below the low. Long/flat only.
- `fast-10`: the base with a 10-day Donchian lookback added, so the signal is
  the mean of the 10- and 20-day states.
- Code: `MidExitTrendSignal`, `DonchianTrendSignal`, `PairedSharpeTest` and
  `eval trend-ablation` as of the commit that adds this file.

## Test

Paired comparison of daily net returns: stationary block bootstrap, 5000
resamples, mean block 20 days, seed 20261119, 90% interval of the Sharpe
difference (arm minus base).

## Commands (each run once)

    for arm in mid-exit fast-10; do
      uv run kavzitrader eval trend-ablation --arm $arm \
        --symbols-file evals/universes/fresh_2022.txt \
        --prereg 2026_11_19_trend_exit_speed_ablation.md \
        --out results/evals/ablation_${arm}_fresh.md
      uv run kavzitrader eval trend-ablation --arm $arm \
        --prereg 2026_11_19_trend_exit_speed_ablation.md \
        --out results/evals/ablation_${arm}_trading.md
    done

## Decision, per arm

- ADOPT: the 90% interval's lower bound is > 0 on the fresh universe AND the
  Sharpe difference is >= 0 on the trading 8. Otherwise REJECT.
- ADOPT earns a forward paper test of its own; the paper rule does not change
  before it. If both arms pass, neither is combined with the other untested.
- No parameter in this file may change after the first run.
