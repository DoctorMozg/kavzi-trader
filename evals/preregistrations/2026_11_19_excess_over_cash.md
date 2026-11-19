# Excess over cash in the funding cross-section report, fixed 2026-11-19

T-bills paid 4-5% a year for most of the funding cross-section's window, so a
market-neutral book's Sharpe overstates what it adds over idle cash
(`.mz/research/2026_11_19_research_trade_algos.md`, test 3). The trend reports
already show Sharpe over cash; `eval funding-xs` now does too, using the same
FRED TB3MS monthly rate (`evals/cash/tb3ms_monthly.csv`, simple daily accrual,
a mark's return day earning that month's rate).

## Re-score (exploratory, decides nothing)

    uv run kavzitrader eval funding-xs \
      --out results/evals/funding_xs_primary_over_cash.md

- The primary's parameters and data are unchanged from
  `2026_11_16_funding_cross_section.md`, whose verdict of record stands.
- The new row is reported in `evals/README.md` next to the original result.
  It counts as a re-score of an existing trial, not a new trial.
