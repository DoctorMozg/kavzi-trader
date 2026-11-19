# Turnover buffer width under higher costs, rules fixed 2026-11-19

The 20% turnover buffer was set by judgement. This sweep checks whether a
different width holds up better if real costs are two or three times the
backtest's 0.05% (`.mz/research/2026_11_19_research_trade_algos.md`, test 6).
The other half of test 6, a maker/taker execution A/B, cannot run: the paper
exchange simulates fills and live orders are not allowed.

## Data

As in `2026_11_19_funding_crowding_overlay.md`: primary the 115 fresh symbols,
secondary the 8 trading symbols, return days 2022-03-15 to 2026-10-31.

## Grid

- Paper rule (Donchian long/flat lookback 20, as everywhere above) with buffer
  bands 0, 0.05, 0.1, 0.2, 0.3, 0.5 at commission 0.0005 x 1, 2 and 3.
- The x1 runs are registered as trials (6 per universe); x2 and x3 are
  sensitivity only.
- Code: `eval buffer-sweep` as of the commit that adds this file.

## Commands (each run once)

    uv run kavzitrader eval buffer-sweep \
      --symbols-file evals/universes/fresh_2022.txt \
      --prereg 2026_11_19_buffer_sweep.md \
      --out results/evals/buffer_sweep_fresh.md
    uv run kavzitrader eval buffer-sweep \
      --prereg 2026_11_19_buffer_sweep.md \
      --out results/evals/buffer_sweep_trading.md

## Decision (fresh universe, x2 cost)

- Flat region: the bands whose net Sharpe is within 0.05 of the best band's.
- Keep 0.2 if it is in the flat region. Otherwise move to the band of the
  region closest to the midpoint of its narrowest and widest band (a tie goes
  to the wider band), and only after the trading 8 at x2 agrees that this band
  is not worse than 0.2.
- The trading-8 table is a sanity check, not a second vote: a move needs the
  fresh universe.
- No parameter in this file may change after the first run.
