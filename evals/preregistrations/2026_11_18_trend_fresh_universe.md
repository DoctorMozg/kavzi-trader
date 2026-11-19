# Trend rule on a never-analysed universe, rules fixed 2026-11-18

The paper plugin trades the Donchian rule with lookback 20, which was picked
after seeing 2022-2026 results on the TRADING and HOLDOUT symbols. Over 11 trend
trials the best deflated Sharpe is 0.89. This test scores the frozen rule once,
on coins no trend test has touched, to see whether its edge belongs to the rule
or to the 16 coins it was tuned on.

## Data

- Universe: the 115 symbols in `evals/universes/fresh_2022.txt`, fixed by a
  mechanical rule before any return on them was computed: every USD-M USDT
  perpetual on data.binance.vision with 1d klines from 2021-12 or earlier and
  still archived in 2022-03, minus the 16 symbols already analysed, stablecoins
  and the BTCDOM and DEFI index contracts. 14 of them were delisted or
  renamed before 2026-10 (LUNA, MATIC, EOS and others); they stay in.
- One symbol dropped for missing data, not for its returns: ICPUSDT has no
  1d bars from 2022-09-22 to 2022-09-26. The completeness check found it
  before any return was computed; every other symbol has continuous daily
  bars from its first close to its last.
- Daily closes: Binance's own 1d klines from the archive (`eval archive
  --dataset klines_1d`), not rolled up from 1m bars. Funding from the archive,
  summed per UTC day.
- Window: return days 2022-03-15 to 2026-10-31 inclusive, the last complete
  archived month. Earlier days only warm up the signal.
- The data was downloaded and checked for missing days before this file was
  committed. No backtest or return on these symbols was computed before then.

## Rule (H1, the paper rule unchanged)

- Donchian long/flat, lookback 20, as in `2026_11_16_trend_following.md`:
  vol window 30, 25% vol target, 2x cap, 20% turnover buffer, commission
  0.0005, daily funding.
- N = 115: each coin's weight is signal x min(0.25 / vol, 2) / 115.
- Before a symbol's first close and after its last close it holds nothing. The
  day after its last close earns no return and pays no funding; the position
  is treated as closed at that last close.
- Code: `DonchianTrendSignal`, `TurnoverBuffer`, `TrendPortfolio` and
  `WeightBacktest` as of the commit that adds this file.

## Benchmark

Equal-weight buy-and-hold of the symbols listed that day (mean of their
close-to-close returns), no costs or funding.

## Command (run once)

    uv run kavzitrader eval trend --lookbacks 20 \
      --symbols-file evals/universes/fresh_2022.txt --to 2026-11-01 \
      --prereg 2026_11_18_trend_fresh_universe.md \
      --out results/evals/trend_fresh_L20.md

## Decision

- PASS: net Sharpe >= 0.5 AND above the benchmark's. Otherwise FAIL.
- PASS: the edge is not specific to the 16 tuning coins, which strengthens the
  case for the paper rule. The lookback-20 forward test
  (`2026_11_16_trend_lookback20_forward.md`) still decides whether it stays.
- FAIL: the lookback-20 result is likely specific to the coins it was chosen
  on. Record it, lower expectations for the forward test, and do not tune the
  rule to rescue this universe.
- Known before running: these are mostly smaller, more volatile coins than
  BTC or ETH. The backtest charges 0.05% per trade and no slippage, so on thin
  coins a PASS overstates what live trading would keep.
- Exploratory only, not part of the decision: the same command on the 101
  symbols still archived in 2026-10 (`evals/universes/fresh_2022_survivors.txt`),
  to show how much dropping delisted coins would have flattered the result.
- No parameter in this file may change after the first run.

## Erratum (2026-11-19, after scoring)

Binance keeps archiving flat zero-volume daily bars after a delisting and during
trading pauses. The run counted them as listed days at 0%, so 39 coins were dead
or paused for part of the window, not 14, and 26 of the 101 "survivors" were
dead. `TrendDataLoader` now treats zero-volume bars as untraded. A labelled
re-run of the same command scored net Sharpe 0.40 (0.01 over cash) against
buy-and-hold's -0.05 (-28.8% a year). That is still below 0.5. The FAIL of
record stands, and the re-run is exploratory.
