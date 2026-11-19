# Evaluation suite

The main commands under `kavzitrader eval` (`kavzi_trader/cli/commands/evals.py`):

| Command | Calls an LLM? | Purpose |
| --- | --- | --- |
| `build-dataset` | no | Download candles, write the frozen triple-barrier cases |
| `run` | **yes, paid** | Push cases through Scout, Analyst and Trader |
| `report` | no | Score a finished run |
| `signals` | no | Measure whether each live confluence signal predicts outcomes |
| `refresh-cache` | no | Fill cached candles, funding and OI (optionally the 5m metrics archive) up to today 00:00 UTC, leave `cases_v1.jsonl` alone |
| `trend` | no | Backtest the daily Donchian trend ensemble against buy-and-hold |
| `funding-xs` | no | Backtest the market-neutral cross-sectional funding rank |
| `trend-ablation` | no | Paired test of one change to the paper trend rule (`--arm`) |
| `buffer-sweep` | no | Trend Sharpe and turnover across buffer widths and cost multiples |
| `vol-forecast` | no | Score 7-day vol forecasters by QLIKE, trade the best in the trend rule |
| `dvol-download` | no | Fetch Deribit's daily DVOL for BTC and ETH into `evals/dvol/` |
| `crash-replay` | no | Replay the paper book minute by minute through one day |
| `crowding-xs` | no | Market-neutral `ls_crowding` book, alpha against BTC |

They share the gitignored cache `data/eval_cache/` (`--cache-dir`): `build-dataset` and `refresh-cache` download into it, the other commands read from it. `trend` and `replay` read the gitignored `data/archive/` mirror instead (`--archive-dir`), which `eval archive` fills from data.binance.vision monthly files and which lags by up to a month. Candle and funding history can always be re-downloaded from Binance. Open interest older than about 30 days cannot (the `metrics` archive below can), so don't delete the OI files.

## Dataset

`cases_v1.jsonl` holds 200 frozen triple-barrier cases (balanced LONG / SHORT / NO_TRADE) over the configured futures symbols at 15m. Candle arrays are not stored in the file.

Rebuild the cache and the dataset (public market data, no API keys):

    uv run kavzitrader eval build-dataset --months 12 --cases 200 --seed 42 --end-date YYYY-MM-DD

Pass the same `--end-date` as in each record's `generator.data_end_ms` to reproduce a dataset exactly. Without it the window ends at today 00:00 UTC (exclusive). Downloads are resumable and a rerun only fetches missing candles. Other options: `--out` (default `evals/cases_v1.jsonl`).

### Labels

Entry is the close of the decision candle. Both a LONG and a SHORT bracket are walked over the next 24h of highs and lows. The stop is 1.5x ATR in every regime (the widest the bot's geometry admits) and the target is 3.0x ATR (ATR_2X style extended to min R:R 2). A bar that touches both SL and TP counts as SL. LONG or SHORT means only that side hit its TP first. If both hit TP, the earlier one wins, and a same-bar tie is NO_TRADE. Anything else is NO_TRADE.

## Running the pipeline

`eval run` makes **paid** Analyst and Trader calls. Provider and models come from `config/config.yaml` (currently direct Anthropic, `claude-sonnet-5-5` Analyst and `claude-opus-5-5` Trader). The key is `KT_ANTHROPIC_API_KEY` (or `KT_OPENROUTER_API_KEY` for OpenRouter agents).

    uv run kavzitrader eval run --bypass-scout --force-trader

A full 200-case run with these two flags cost about $4.60 on the models above.

The command first runs a deterministic pre-pass (no LLM) to find which cases reach the Analyst, then a 5-case dry run on cases that do. It prints measured cost and latency per case and a projection for the rest, then asks `Continue with the remaining cases?`. Add `--yes` to skip the question.

| Flag | Meaning |
| --- | --- |
| `--bypass-scout` | Record the Scout verdict but continue to the Analyst on SKIP |
| `--force-trader` | Run the Trader on cases the Analyst gate stopped, scored separately |
| `--limit N` | Label-balanced first N cases (the dataset file is grouped by label) |
| `--cases ID,ID` | Only these case ids. Unknown ids are an error |
| `--concurrency N` | Parallel cases, default 4 |
| `--dataset FILE` | Default `evals/cases_v1.jsonl` |
| `--resume RUN_ID` | Continue an interrupted run |

Run ids look like `run_20261115T120000Z`. Output goes to `results/evals/<run_id>.jsonl` (append-only, one case per line) and `results/evals/<run_id>.header.json` (models, effort, flags, git hash).

If you decline at the prompt or the run dies, resume it:

    uv run kavzitrader eval run --resume run_20261115T120000Z

Finished cases are skipped, so you don't pay for them again. Cases that errored rerun. Resume refuses to start if `--bypass-scout`, `--force-trader` or the models differ from the stored header.

## Scoring a run

    uv run kavzitrader eval report --run run_20261115T120000Z

No LLM calls. Writes `results/evals/<run_id>.report.md` (override with `--out`) and prints a short summary. The report covers the stage funnel, decision-vs-label matrices, per-stage stats, simulated R against baselines, and ops/cost.

## Trend backtest

    uv run kavzitrader eval trend
    uv run kavzitrader eval trend --variant long-short --lookbacks 20
    uv run kavzitrader eval trend --symbols DOGEUSDT,LTCUSDT,DOTUSDT,BCHUSDT,ATOMUSDT,TRXUSDT,ETCUSDT,FILUSDT

No LLM calls. Rules are fixed in `evals/preregistrations/2026_11_16_trend_following.md`. Reads 1m klines and funding from the archive (`eval archive`, or `eval archive --symbols ...` for symbols outside `trading.symbols`), rolls them into 4h candles (`archive_series.py`) and folds every 6 candles into a UTC day (`trend_data_loader.py`). Days with fewer than 6 candles are dropped, and a gap in the daily series is an error.

Per symbol and lookback L, the Donchian state is 1 when the close is above the highest close of the previous L days, 0 (long/flat) or -1 (long/short) when it is below the lowest, else unchanged (`strategies/trend/donchian_trend_signal.py`). The signal is the mean of the lookback states. Target weight is `signal * min(0.25 / vol, 2.0) / N`, where `vol` is the 30-day daily log-return std x sqrt(365) and N is the number of symbols. Weights set at a close earn the next day's return.

`strategies/trend/turnover_buffer.py` trades a symbol only when its target is zero, flips sign, or differs from the held weight by more than 20% of it. `trend_portfolio.py` charges `paper.commission_rate` on traded weight and funding on held weight (longs pay positive funding). The benchmark is equal-weight, daily-rebalanced buy-and-hold with no costs or funding.

Options:

- `--variant long-flat|long-short|vol-hold|sma200` (default `long-flat`, the pre-registered rule). `vol-hold` is always long with the trend sizing; `sma200` is unlevered long above the 200-day average (use it with `--symbols BTCUSDT`).
- `--lookbacks 20,40,80`: days, comma-separated. The pre-registered rule uses all three.
- `--symbols`: default is the 8 trading symbols. Score the 8 HOLDOUT symbols (DOGE LTC DOT BCH ATOM TRX ETC FIL) with a second run.
- `--symbols-file`: one symbol per line, `#` comments allowed, e.g. `evals/universes/fresh_2022.txt`. Use it instead of `--symbols`. Zero-volume daily bars count as untraded and hold nothing: Binance keeps archiving flat zero-volume bars after a delisting and during trading pauses, so a coin still in the archive is not necessarily still traded.
- `--prereg`: the preregistration the report cites. Without it the report cites the original trend file and says both symbol sets must pass.
- `--from` / `--to` (default 2022-03-15 to 2026-11-15, `--to` exclusive): days outside the window only warm up the lookbacks.
- `--archive-dir` (default `data/archive`), `--out` (default `results/evals/trend_<UTC time>.md`).

It prints net Sharpe, benchmark Sharpe and `criterion met` (net Sharpe >= 0.5 and above the benchmark's). The pre-registered PASS needs that on both symbol sets. The report has return, volatility, Sharpe, max drawdown, turnover, cost and funding drag, and Sharpe per year, for the strategy and the benchmark.

Wide universes only need daily bars, not 1m history: `eval archive --dataset klines_1d --dataset funding --symbols ...`. The loader uses 1d bars when they exist and falls back to 1m.

### Walk-forward lookback choice

    uv run kavzitrader eval trend-walkforward --prereg <file>

Each calendar year from `--test-from` (default 2022-01-01) to `--to` (default 2026-11-01, exclusive) trades the single lookback from `--lookbacks` (default 10,20,30,40,60,80,120) with the best net Sharpe from `--train-from` (default 2020-12-15) to the day before that year; ties go to the shorter lookback (`evals/walk_forward.py`). The chosen rules are stitched into one weight series (`scheduled_signal.py`) and the turnover buffer runs over it without a reset at year ends. The report lists each year's choice with every candidate's training Sharpe, the usual summary of the stitched result, and fixed `--hindsight-lookback` (default 20) over the same days for comparison. Takes `--symbols`/`--symbols-file`, `--archive-dir` and `--out` (default `results/evals/walkforward_<UTC time>.md`), and registers one trial.

### Research trials (2026-11-19)

Seven tests from `.mz/research/2026_11_19_research_trade_algos.md`, each preregistered in `evals/preregistrations/2026_11_19_*.md`, committed, then run once on 2026-11-19. Trend arms use return days 2022-03-15 to 2026-10-31 and the paired block bootstrap in `validation/paired_sharpe_test.py` (5000 resamples, 20-day blocks, 90% interval). Each run registers a trial.

| Test | Result | Decision |
| --- | --- | --- |
| Funding-crowding overlay (`trend-ablation --arm funding-crowding`) | Max drawdown smaller on both sets (fresh -16.6% to -14.5%, trading -19.3% to -18.5%), but Sharpe fell (0.404 to 0.266, 0.640 to 0.578) | REJECT |
| Mid-channel exit (`--arm mid-exit`) | Fresh 0.404 to 0.688, interval [+0.009, +0.524]; trading 0.640 to 0.905; drawdowns smaller on both | ADOPT; in the paper rule since 2026-11-20 (`exit_rule: mid`) |
| Fast 10-day component (`--arm fast-10`) | Fresh 0.404 to 0.374, interval [-0.242, +0.164] | REJECT |
| Buffer width (`buffer-sweep`) | Sharpe rises with width at every cost on both sets; fresh at 2x cost: 0.388 at 0.2, best 0.414 at 0.5 | Keep 0.2 (inside the 0.05 flat region) |
| Vol forecast (`vol-forecast`) | QLIKE against the 30-day estimate's 0.704: HAR 0.545 (p 0.001), LightGBM 0.555 (p 0.001), Chronos-2 0.748 (worse). Trading HAR: Sharpe 0.640 to 0.565, interval [-0.184, +0.039] | REJECT for trading; HAR is the better forecaster but not the better sizer |
| Crash replay 2025-10-10 (`crash-replay`) | Book BTC 0.113, ETH 0.060, BNB 0.053. BNB's stop fired at 21:19, filled -34.4%, on both triggers (mark low 866.6 under the 879.3 stop). Day: no stop -2.22%, as live -3.40%, with halving -2.10%. Halving over the window: Sharpe 0.640 to 0.624 | Halving: ADOPT; in the paper rule since 2026-11-20 (`vol_spike`). Trigger: keep the last price |
| `ls_crowding` market-neutral (`crowding-xs`) | Net Sharpe -0.72, alpha -8.4% a year (t -1.25), beta -0.01 | FAIL: `ls_crowding` closes |

- The mid-exit pass is narrow: its fresh lower bound is +0.009, and the bound is not deflated for the trend family's trial count.
- Both passes went into the paper rule on 2026-11-20, by the owner's decision, without the forward paper tests their preregistrations asked for; the two were never scored together. The lookback-20 forward test (`2026_11_16_trend_lookback20_forward.md`) is a backtest on new data and still stands, but paper fills no longer follow its rule, so its execution-parity check no longer applies.
- DVOL helps forecasting on BTC and ETH (HAR+DVOL QLIKE 0.456 against HAR's 0.550, p < 0.0001); it covers 2 of 8 coins, so it was informational only.
- The 30% stop cost money in the replay: the BNB wick recovered within minutes, so selling at the low lost 1.2% of equity against holding.
- Not run: the maker/taker execution A/B (test 6). The paper exchange simulates fills and live orders are not allowed, so no fill data exists.

### Closed lines

Each of these failed a preregistered test. Don't loosen a threshold, swap a window or add a filter until one passes: that is fitting noise. A new idea gets a new preregistration with out-of-sample data.

- LLM pipeline as the trading strategy (lost to buy-and-hold in the July 2026 replay). It stays available, not active.
- Candle and funding confluence signals, and loosening Scout or Analyst gates (no lift above fees, 2026-11-16).
- Funding carry across coins (`eval funding-xs`, FAIL at 0.43; 0.25 over cash in the 2026-11-19 re-score).
- Trend ensemble 20/40/80 (FAIL at 0.45 / 0.50).
- Trend lookback 20 on the fresh 115-coin universe (FAIL at 0.37, -0.03 over cash; 0.40 after the zero-volume fix).
- Long above the 200-day average on the fresh 115-coin universe (FAIL at -0.15, -0.29 over cash). The BTC-only pass of 2026-11-17 is treated as a single-asset accident.
- SHORT `smart_vs_crowd` on fresh coins (FAIL, fired +0.015 R against a 0.025 R fee).
- Halving trend longs while funding is crowded (Sharpe fell on both sets, 2026-11-19).
- A fast 10-day Donchian component (2026-11-19).
- HAR, LightGBM or Chronos-2 vol forecasts as the trend sizer (HAR lowered Sharpe; Chronos-2 lost to the 30-day estimate, 2026-11-19).
- `ls_crowding` in any direction: the market-neutral book lost money (alpha -8.4%, t -1.25), so the SHORT pass of 2026-11-18 was market drift.
- Switching the paper rule to lookback 10 because walk-forward picked it: that choice was made after seeing the result and needs its own forward test.

## Funding cross-section backtest

    uv run kavzitrader eval funding-xs
    uv run kavzitrader eval funding-xs --hold-days 1 --legs 2

No LLM calls. Rules are fixed in `evals/preregistrations/2026_11_16_funding_cross_section.md`. Needs 4h candles and funding for the symbols (`refresh-cache --interval 4h`). Every `--hold-days` days at 00:00 UTC, counted from 2022-03-15, each symbol is scored by the mean of its last 9 funding settlements. The top `--legs` scores are shorted and the bottom `--legs` longed, each at 1/(2 x legs) of equity, so gross is 1.0 and net 0. P&L is the legs' price move plus funding settled during the hold (a short receives positive funding). Cost is `paper.commission_rate` x the weight change at each rebalance (`funding_xs_backtester.py`, `funding_xs_leg_picker.py`).

Options:

- `--symbols`: default is all 16 cached symbols as one cross-section.
- `--hold-days` (default 3) and `--legs` (default 3): the pre-registered values. Other values are exploratory.
- `--cache-dir`, `--out` (default `results/evals/funding_xs_<time>.md`).

It prints net Sharpe, Sharpe over cash (3-month T-bill, `evals/cash/tb3ms_monthly.csv`), annual return and PASS or FAIL (net Sharpe >= 0.5, net return > 0, and positive net return in at least 3 calendar years). The report splits return into price, funding and cost, gross against net. The primary run's re-score of 2026-11-19 gives 0.42 net and 0.25 over cash.

## Signal edge

    uv run kavzitrader eval signals
    uv run kavzitrader eval signals --bracket 1.5:3:96 --bracket 1:2:48 --funding
    uv run kavzitrader eval signals --oi --stride 5
    uv run kavzitrader eval refresh-cache --interval 4h --months 60
    uv run kavzitrader eval signals --interval 4h --stride 1 --candidates --bracket 1:2:6 --bracket 1.5:3:12
    uv run kavzitrader eval refresh-cache --interval 4h --months 60 --metrics
    uv run kavzitrader eval signals --interval 4h --stride 1 --metrics --bracket 1.5:3:12

No LLM calls. Asks whether each live confluence signal predicts outcomes, before any LLM sees the setup. It samples every Nth cached bar of the chosen interval, computes indicators with the live calculator over the trailing history window, and gets flags from the live `ConfluenceCalculator`. Each bar is labelled with every `--bracket SL_ATR:TP_ATR:HORIZON_BARS` (repeatable, default `1.5:3:96`). Horizons are in bars of the interval. Zero-volume bars are dropped, so a delisted coin ends at its last traded bar. The positioning signals (`--metrics`) rank each ratio among the last trailing-window known ratios; a bar whose latest ratio is over a day old has no rank and fires nothing (added 2026-11-19, after the fresh SHORT test; earlier `--metrics` results carried the last ratio forward with no limit).

Per signal and side, the report (`results/evals/signals_<UTC time>.md`, override with `--out`) gives:

- how often it fires
- mean R when fired and when not fired
- **lift**: fired minus not-fired mean R. This cancels market drift, so the verdict uses lift, not raw mean R
- a 95% interval, widened by sqrt(horizon / stride) because neighbouring samples share outcome windows. A signal counts as having edge only when |lift| exceeds that interval
- win rate and score buckets
- the taker round-trip fee in R, from `paper.commission_rate`. Lift has to clear this to be tradable

Options:

- `--stride N` (default 17): keep it coprime with the bars per day (96 at 15m, 24 at 1h, 6 at 4h). A stride of 16 sampled the same 6 times of day and biased the volume signals (above-average-volume rate swung 27% to 43% by phase).
- `--funding`: downloads Binance funding history (public endpoint, no key) and scores the live funding signal: z-score of the latest settlement over the last 100 settlements, as live.
- `--interval` (default: trading interval): reads `<SYMBOL>_<interval>.csv.gz`. If the cache is missing it errors with a hint to run `eval refresh-cache --interval X`.
- `--from` / `--to` (UTC days, `--to` exclusive): only bars closing inside the window are sampled. Bars before it still warm up the indicators, so a window scores its bars exactly as a full run does. Use it to check a lead year by year.
- `--candidates`: also scores signals the live bot does not use yet:
  - `taker_flow`: taker-buy share of volume over the last 4 bars, ranked within the trailing history window. Top third fires LONG, bottom third fires SHORT.
  - `htf_trend`: the live 1h trend (EMA20/EMA50 plus RSI from `indicators/htf.py`) agrees with the side. 15m only.
  - `btc_lead`: BTCUSDT's return over the last 4 bars, ranked the same way, applied to every other symbol.
- `--oi` (implies `--funding`): downloads open interest (15m at the 15m interval, see below) and scores `oi_supports_direction` and `oi_funding_divergence` through the live `OrderFlowCalculator`. Binance serves only about the last 30 days of OI, so only bars inside that window, with a full 24h of OI history, are sampled. Use a small stride such as 5. The cache keeps old rows, so running `eval refresh-cache` weekly grows the OI history past Binance's ~30-day limit and adds the new candles, without which new bars won't be sampled.
- `--metrics` (implies `--funding`, excludes `--oi`): scores the same two OI signals from the data.binance.vision `data/futures/um/daily/metrics/` archive instead of `openInterestHist`, plus two positioning signals. The archive has 5-minute rows of OI, the global long/short account ratio and the top-trader long/short position ratio, so OI history is about 5 years instead of about 30 days and `--oi`'s window limit does not apply. Each bar uses the latest row at or before its close. Missing days are downloaded into the cache on demand. Start dates: BTC 2021-11-14, the other 15 symbols 2021-12-01. The top-trader ratio is missing for most of 2022. Rows without a positive ratio are skipped, so in that stretch `smart_vs_crowd` reads the last valid value, which is stale. Treat 2022 results for it with care.
  - `ls_crowding`: global account ratio, ranked within the trailing history window. Bottom third (crowd short) fires LONG, top third fires SHORT.
  - `smart_vs_crowd`: log(top-trader position ratio) - log(global account ratio), ranked the same way. Top third fires LONG, bottom third SHORT.

### Refreshing the cache

    uv run kavzitrader eval refresh-cache --interval 4h --months 60

No LLM calls. Options: `--interval` (default: trading interval), `--months` (default 12), `--cache-dir`, `--symbols` (default the trading symbols), `--metrics` (also download the 5-minute metrics archive and print its row count per symbol). Fills candles, funding and OI up to today 00:00 UTC and never touches `cases_v1.jsonl`. Reruns fetch only the missing head or tail. OI uses the largest openInterestHist period that doesn't exceed the interval, capped at 30m, so 1h and 4h use `oi_30m`. It prints one line per symbol with candle count, date range, funding rows and OI rows.

`scripts/refresh_eval_cache.sh` refreshes 15m, 1h and 4h for the trading symbols, then 4h only for 8 extra symbols (DOGE LTC DOT BCH ATOM TRX ETC FIL) that the forward test needs. It logs to `results/logs/refresh_eval_cache_<date>.log`. Run it weekly: Binance serves about the last 30 days of OI, so a monthly run in a 31-day month can lose a day.

Schedule it with a systemd user timer. `~/.config/systemd/user/kavzi-eval-refresh.service`:

    [Unit]
    Description=Refresh KavziTrader eval cache (candles, funding, OI)
    Wants=network-online.target
    After=network-online.target

    [Service]
    Type=oneshot
    ExecStart=/path/to/kavzitrader/scripts/refresh_eval_cache.sh

`~/.config/systemd/user/kavzi-eval-refresh.timer`:

    [Unit]
    Description=Weekly KavziTrader eval cache refresh

    [Timer]
    OnCalendar=Mon *-*-* 03:00:00
    Persistent=true
    RandomizedDelaySec=15min

    [Install]
    WantedBy=timers.target

Enable it:

    systemctl --user daemon-reload && systemctl --user enable --now kavzi-eval-refresh.timer

`Persistent=true` runs a missed refresh at the next login or boot, which cron would skip. A user timer fires only while the user's systemd instance is up, so if the machine has no open session on Monday, run `loginctl enable-linger $USER` (optional) to keep that instance alive.

Cron alternative, Mondays at 03:00:

    0 3 * * 1 /path/to/kavzitrader/scripts/refresh_eval_cache.sh

Cache files in `data/eval_cache/`: `<SYMBOL>_15m.csv.gz` (and `<SYMBOL>_<interval>.csv.gz` for other intervals), `<SYMBOL>_funding.csv.gz`, `<SYMBOL>_oi_15m.csv.gz`, `<SYMBOL>_oi_30m.csv.gz`, `<SYMBOL>_metrics_5m.csv.gz` (metrics archive, from `--metrics`).

### What we found (snapshot, 2026-11-16)

- 12 months x 8 symbols, six brackets: no candle or funding signal showed lift above chance. 3 of 60 candle tests passed, about what chance gives at 95%.
- The largest lifts (+0.05 to +0.07 R) were far below the 0.15 to 0.30 R round-trip fee.
- 27 days of OI: `oi_supports_direction` leaned positive (+0.04 to +0.14 R) but was not significant and still below the fee.
- Candidates on 15m (12 months, six brackets): none beat the fee. `taker_flow` lift was negative (-0.04 to -0.08 R, significant in 4 cells), so heavy taker buying or selling slightly reverses, still far below the 0.15 to 0.29 R fee. `htf_trend` LONG was +0.06 R in one cell. `btc_lead` showed nothing.
- Longer timeframes cut the fee in R: about 0.07 to 0.14 R at 1h and 0.03 to 0.07 R at 4h. 1h, 12 months: no signal with positive lift (two negative cells).
- 4h, 12 months: `ema_alignment` lift was positive in all 8 side and bracket cells (+0.04 to +0.23 R). Over 5 years (79k bars) it shrank to +0.01 to +0.05 R and was not significant, so the 12-month result was mostly one regime.
- 4h, 5 years: `taker_flow` LONG lift was +0.04 to +0.075 R in all 4 brackets, above the fee in two, but only 2 of 104 tests passed, fewer than chance predicts. It is a lead to check out of sample (for example per year), not an edge.
- 4h `taker_flow` LONG, year by year at `1.5:3:12`: lift was positive in all 5 years (+0.02 to +0.14 R) and +0.062 over 5 years, above the 0.036 R fee. But the fired bars themselves averaged only +0.027 R, below the fee: the signal makes LONG entries less bad than average, it does not make them profitable on its own. 1h agrees in sign but is weaker.
- Scout `trend_vol_ratio_min` 1.2 instead of 0.8 (15m, `--scout-vol-min`): it halves the TREND_CONTINUATION calls and makes the LONG ones worse in all six brackets. The calls already have negative lift at 0.8.
- RSI above 70 two bars running (`rsi_exhausted`): LONG after it did better than average (+0.09 to +0.21 R lift), so a guard that vetoes those LONGs would cut the better trades.
- Combinations on 4h (`--combo`, rules fixed before scoring): 16 pairs of `taker_flow` with another signal, trained on the 8 trading symbols 2022 to 2025. The best, LONG `taker_flow+rsi_exhausted` (+0.18 R on 1.8k bars), failed on 8 never-analysed symbols (DOGE LTC DOT BCH ATOM TRX ETC FIL, `--symbols`): +0.011 R against a 0.035 R fee. Unselected but worth a fresh test: SHORT `taker_flow+funding_favorable` cleared the fee on both sets (+0.055 and +0.079 R), with intervals that still reach below it.
- That SHORT rule is now frozen in `evals/preregistrations/2026_11_16_short_taker_funding.md`: bracket `1.5:3:12`, 16 symbols, bars from 2026-11-15 to 2027-11-15. It is scored once, after the 48h outcomes are complete (on or after 2027-11-17), with no early looks.
- Implication: loosening the Scout or Analyst gates would trade noise. A new feature should show lift above the fee in `eval signals` first.
- Trend 20/40/80, long/flat (`eval trend`, pre-registered): **FAIL.** Net Sharpe 0.446 on TRADING and 0.496 on HOLDOUT against a 0.5 bar. It beat equal-weight buy-and-hold on both (Sharpe 0.31 on TRADING, 0.05 on HOLDOUT). Max drawdown was -19% vs -73%. Moving the daily close by 4h shifts the Sharpe by about 0.1 either way, so the result is within noise of the bar. Lookback 20 alone scored 0.64 on TRADING and 0.65 on HOLDOUT, but that was seen after the fact. It is frozen as a forward test in `evals/preregistrations/2026_11_16_trend_lookback20_forward.md` and scored once, on or after 2027-11-16.
- Trend on unused 2020-12-15 to 2022-03-14 history (TRADING only, from the archive, rules in `evals/preregistrations/2026_11_17_trend_2021_backfill.md`): both rules **PASS**, but the evidence is weak. 20/40/80 scored net Sharpe 2.35 against buy-and-hold's 2.25, and lookback 20 scored 2.61. Max drawdown was -11% against -58%. The window is a bull market, and the edge over buy-and-hold comes from vol targeting (15% vol against 102%), not higher returns (40% a year against 482%). In 2021 alone, 20/40/80 trailed buy-and-hold (2.74 against 2.92). In Q1 2022 both rules did worse than buy-and-hold. The 2020 row covers only 17 days. Over all six trend trials, the best (lookback 20 here) has a deflated Sharpe of 0.90, below the usual 0.95 bar. The lookback-20 forward test still decides the paper plugin.
- Trend vs simpler rules (`eval trend --variant vol-hold|sma200`, TRADING, rules in `evals/preregistrations/2026_11_17_trend_vs_simple_benchmarks.md`). Q1, does the Donchian signal beat holding with the same vol sizing? Barely: on 2022-03-15 to 2026-11-14, vol-hold scored net Sharpe 0.43 against 0.47 for 20/40/80, so the signal is credited and nothing changes. Vol-hold earned more (7.8% a year against 5.6%) but had twice the drawdown (-40% against -19%), so the signal's value is drawdown control. On the 2021 backfill vol-hold scored 1.94. Q2, BTC long above its 200-day SMA, unlevered: **PASS** on the main window, net Sharpe 0.78 against BTC buy-and-hold's 0.54, drawdown -32% against -67%. That makes it a candidate arm, not an adopted strategy. On the 2021 backfill it scored 0.15 against 1.12: it held through the May 2021 crash, whipsawed 19 times, and paid about 27% a year in funding, ending -10% a year while BTC doubled. Over all 11 trend trials, the best (lookback 20, 2021 backfill) has a deflated Sharpe of 0.89; PBO is 0.16.
- Lookback 20 on 115 never-analysed coins (`evals/preregistrations/2026_11_18_trend_fresh_universe.md`, universe `evals/universes/fresh_2022.txt`, 14 delisted coins kept in): **FAIL.** Net Sharpe 0.37 against the 0.5 bar, 2022-03-15 to 2026-10-31. Buy-and-hold of the same coins scored -0.01 and lost 22% a year with a -84% drawdown; the rule made 3.4% a year with a -17% drawdown. The rule clearly beats holding these coins, but the 0.64 Sharpe on TRADING does not carry over at full strength, so treat it as partly specific to those coins. Exploratory, on the 101 survivors: 0.39, so survivorship would have flattered it only slightly. Per the preregistration the rule is not tuned to rescue this universe. Erratum (2026-11-19): the archive keeps flat zero-volume bars after a delisting, and this run counted them as listed days at 0%. It also held 39 dead or paused coins, not 14, and 26 of the "101 survivors" were dead. A labelled re-run with zero-volume bars as untraded scored 0.40 (0.01 over cash), with buy-and-hold at -0.05 and -29% a year. The FAIL of record stands.
- 200-day average on 115 never-analysed coins (`evals/preregistrations/2026_11_18_sma200_fresh_universe.md`, zero-volume bars untraded, run 2026-11-19): **FAIL.** Net Sharpe -0.15 against the 0.5 bar and the benchmark's -0.05, -0.29 over cash; -8.3% a year with a -56% drawdown (buy-and-hold -28.8% a year, -90%). It lost less than holding, but it lost. Per year: -2.64, 0.51, 0.25, -1.69, -0.30 for 2022 to 2026. 15 trend trials now.
- Walk-forward lookback choice (`eval trend-walkforward`, `evals/preregistrations/2026_11_18_trend_walk_forward.md`, TRADING): **PASS.** Choosing each year's lookback from earlier years only scored net Sharpe 0.59 against buy-and-hold's 0.28 on 2022-01-01 to 2026-10-31, at 7.8% a year with a -21% drawdown (buy-and-hold -3.5% a year, -76%). It picked lookback 10 every year, the shortest candidate, not 20. Fixed lookback 20 scored 0.57 over the same days, so hindsight in choosing 20 added nothing; short lookbacks as a group hold up without it. Yearly Sharpe was -0.72, 1.94, 1.85, -0.55 and -0.17 for 2022 to 2026: two good years carry the result. Lookback 10 sits at the edge of the grid, and switching the paper rule to it would be a new choice that the frozen lookback-20 forward test does not cover. Over all 14 trend trials the deflated Sharpe of the best is 0.90 (0.95 is the usual bar); PBO is 0.16.
- Against cash (added 2026-11-18): reports now show Sharpe over the 3-month US T-bill rate (`evals/cash/tb3ms_monthly.csv`, FRED TB3MS, monthly). Cash paid 4.2% a year over 2022-03-15 to 2026-10-31. Over cash, lookback 20 on TRADING scores 0.36 (0.64 raw), the walk-forward 0.31 (0.59), and the 115 fresh coins -0.03 (0.37): on coins it was not tuned on, the rule earned what T-bills paid with 10% volatility. All earlier bars and verdicts stay on raw Sharpe; quote both from now on.
- LLM pipeline, July 2026 replay (`eval replay --strategy llm_pipeline --record`, the first month after the models' training cutoff, about $29 of calls): equity 10,000 to 9,604 (-4.0%) against +7.8% for equal-weight buy-and-hold. 20 fills, 16 of them stopped out. Holding the Trader's 57 entry decisions fixed and replaying them on 1m bars, the called direction was right only 35-40% of the time at 1h, 4h, 24h and 72h, the 5th percentile of random-side draws. 3 of 144 stop, target and hold variants were positive, about what selection noise gives. Published live and post-cutoff tests find no net edge for LLMs choosing direction either (`.mz/research/2026_11_17_research_trading_bot_sota.md`). Decision: no more paid recording for this pipeline, and `strategy.active` now defaults to `trend_following`.
- Shadow news gate, July-October 2026 replay (`eval gate-replay`, Part A of `evals/preregistrations/2026_11_17_trend_news_gate.md`, run 2026-11-18): all 45 votes on the 15 trend entries were KEEP, so 0 vetoes and veto value +0.00%. Ten entries had no headline about their own coin, only market-wide news. The replay is uninformative, which by the rules means the gate keeps running in shadow and Part B (live log, at least 40 entries) is scored on or after 2027-11-17.
- Funding cross-section (`eval funding-xs`, pre-registered): **FAIL.** Net Sharpe 0.425, +7.6%/yr. Funding carry was +9.0%/yr, price +6.8%/yr, costs -5.6%/yr.
- Metrics archive (`eval signals --metrics`, 4h, bracket `1.5:3:12`, both symbol sets, rules in `evals/preregistrations/2026_11_16_positioning_metrics.md`): `oi_supports_direction` and `oi_funding_divergence` over 5 years FAIL. SHORT `ls_crowding` (fired +0.083 / +0.065 R against a ~0.035 R fee) and SHORT `smart_vs_crowd` (+0.057 / +0.072 R) PASS, but not STRONG, since their lower bounds are below the fee. They are the first pre-registered passes. All LONG versions failed.

- SHORT crowding on fresh coins (`evals/preregistrations/2026_11_18_short_crowding_fresh.md`, 99 of the 101 survivors with traded bars, bars closing 2023-06-18 to 2026-11-14, 645,661 bars, run 2026-11-19): SHORT `ls_crowding` **STRONG PASS** by the rules: fired +0.048 ±0.017 R against a 0.025 R fee, lift +0.020 ±0.021. SHORT `smart_vs_crowd` **FAIL**: fired +0.015 R, lift -0.027. Read the pass with care: shorting any bar of these coins earned +0.034 R, already above the fee, because most of them fell; the lift interval reaches zero, and slippage on thin coins is not modelled. Most of the fired mean is drift in a falling sample. Per the preregistration it earns a paper preregistration of its own (sizing, exits, forward window) and is not traded before one exists.

Rerun the command before relying on these numbers, since they describe one data window.
