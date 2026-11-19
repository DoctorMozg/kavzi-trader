# Funding-crowding sizing overlay on the trend rule, rules fixed 2026-11-19

BIS ("Crypto carry", 2025) finds that high perpetual funding predicts crashes,
not lower mean returns. If so, cutting longs while funding is crowded should
shrink drawdowns without costing Sharpe. Two of the 2026-11-19 researchers
proposed this rule independently (`.mz/research/2026_11_19_research_trade_algos.md`,
test 1).

## Data

- Primary: the 115 symbols of `evals/universes/fresh_2022.txt`. Secondary: the
  8 trading symbols. Daily closes and funding from the archive, as in
  `2026_11_18_trend_fresh_universe.md` (zero-volume bars count as untraded).
- Window: return days 2022-03-15 to 2026-10-31 inclusive.
- Checked before this file was committed (row counts only, no returns): on the
  trading 8 every symbol has every day of the window. BNBUSDT's 596 zero-funding
  days are real: Binance archives `rate 0.0` for those settlements. In the fresh
  universe 71 symbols cover the whole window, 39 end early (delisted), 4 have
  delist/relist gaps (CTK, CVC, LIT, TLM) and BTCSTUSDT has no traded day.

## Rule

- Base: the paper rule, Donchian long/flat lookback 20, vol window 30, 25% vol
  target, 2x cap, 20% turnover buffer, commission 0.0005, daily funding.
- Arm: the base weights, with a coin's long weight halved on any day its 7-day
  mean of daily funding is strictly above the 90th percentile of the same
  7-day mean over the trailing 365 days (today included, at least 180 days of
  history; with less history it is never crowded). Strict, so flat baseline
  funding never counts as crowded. Applied before the turnover buffer.
- Code: `FundingCrowdingOverlay` and `eval trend-ablation` as of the commit
  that adds this file.

## Commands (each run once)

    uv run kavzitrader eval trend-ablation --arm funding-crowding \
      --symbols-file evals/universes/fresh_2022.txt \
      --prereg 2026_11_19_funding_crowding_overlay.md \
      --out results/evals/ablation_funding_crowding_fresh.md
    uv run kavzitrader eval trend-ablation --arm funding-crowding \
      --prereg 2026_11_19_funding_crowding_overlay.md \
      --out results/evals/ablation_funding_crowding_trading.md

## Decision

- ADOPT: on both universes the arm's max drawdown is smaller than the base's
  AND its net Sharpe minus the base's is >= 0. Otherwise REJECT.
- ADOPT earns a paper-trading change of its own; nothing changes before it.
- The vol target stays fixed, so the arm runs at lower average exposure. A
  smaller drawdown from less exposure alone counts; that is the point of it.
- The 90% bootstrap interval in the report is shown but does not decide: on 8
  coins it is about 1.5 Sharpe wide.
- No parameter in this file may change after the first run.
