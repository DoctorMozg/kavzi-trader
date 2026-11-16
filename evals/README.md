# Evaluation suite

Seven commands under `kavzitrader eval` (`kavzi_trader/cli/commands/evals.py`):

| Command | Calls an LLM? | Purpose |
| --- | --- | --- |
| `build-dataset` | no | Download candles, write the frozen triple-barrier cases |
| `run` | **yes, paid** | Push cases through Scout, Analyst and Trader |
| `report` | no | Score a finished run |
| `signals` | no | Measure whether each live confluence signal predicts outcomes |
| `refresh-cache` | no | Fill cached candles, funding and OI (optionally the 5m metrics archive) up to today 00:00 UTC, leave `cases_v1.jsonl` alone |
| `trend` | no | Backtest the daily Donchian trend ensemble against buy-and-hold |
| `funding-xs` | no | Backtest the market-neutral cross-sectional funding rank |

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

- `--variant long-flat|long-short` (default `long-flat`, the pre-registered rule).
- `--lookbacks 20,40,80`: days, comma-separated. The pre-registered rule uses all three.
- `--symbols`: default is the 8 trading symbols. Score the 8 HOLDOUT symbols (DOGE LTC DOT BCH ATOM TRX ETC FIL) with a second run.
- `--from` / `--to` (default 2022-03-15 to 2026-11-15, `--to` exclusive): days outside the window only warm up the lookbacks.
- `--archive-dir` (default `data/archive`), `--out` (default `results/evals/trend_<UTC time>.md`).

It prints net Sharpe, benchmark Sharpe and `criterion met` (net Sharpe >= 0.5 and above the benchmark's). The pre-registered PASS needs that on both symbol sets. The report has return, volatility, Sharpe, max drawdown, turnover, cost and funding drag, and Sharpe per year, for the strategy and the benchmark.

## Funding cross-section backtest

    uv run kavzitrader eval funding-xs
    uv run kavzitrader eval funding-xs --hold-days 1 --legs 2

No LLM calls. Rules are fixed in `evals/preregistrations/2026_11_16_funding_cross_section.md`. Needs 4h candles and funding for the symbols (`refresh-cache --interval 4h`). Every `--hold-days` days at 00:00 UTC, counted from 2022-03-15, each symbol is scored by the mean of its last 9 funding settlements. The top `--legs` scores are shorted and the bottom `--legs` longed, each at 1/(2 x legs) of equity, so gross is 1.0 and net 0. P&L is the legs' price move plus funding settled during the hold (a short receives positive funding). Cost is `paper.commission_rate` x the weight change at each rebalance (`funding_xs_backtester.py`, `funding_xs_leg_picker.py`).

Options:

- `--symbols`: default is all 16 cached symbols as one cross-section.
- `--hold-days` (default 3) and `--legs` (default 3): the pre-registered values. Other values are exploratory.
- `--cache-dir`, `--out` (default `results/evals/funding_xs_<time>.md`).

It prints net Sharpe, annual return and PASS or FAIL (net Sharpe >= 0.5, net return > 0, and positive net return in at least 3 calendar years). The report splits return into price, funding and cost, gross against net.

## Signal edge

    uv run kavzitrader eval signals
    uv run kavzitrader eval signals --bracket 1.5:3:96 --bracket 1:2:48 --funding
    uv run kavzitrader eval signals --oi --stride 5
    uv run kavzitrader eval refresh-cache --interval 4h --months 60
    uv run kavzitrader eval signals --interval 4h --stride 1 --candidates --bracket 1:2:6 --bracket 1.5:3:12
    uv run kavzitrader eval refresh-cache --interval 4h --months 60 --metrics
    uv run kavzitrader eval signals --interval 4h --stride 1 --metrics --bracket 1.5:3:12

No LLM calls. Asks whether each live confluence signal predicts outcomes, before any LLM sees the setup. It samples every Nth cached bar of the chosen interval, computes indicators with the live calculator over the trailing history window, and gets flags from the live `ConfluenceCalculator`. Each bar is labelled with every `--bracket SL_ATR:TP_ATR:HORIZON_BARS` (repeatable, default `1.5:3:96`). Horizons are in bars of the interval.

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
- Funding cross-section (`eval funding-xs`, pre-registered): **FAIL.** Net Sharpe 0.425, +7.6%/yr. Funding carry was +9.0%/yr, price +6.8%/yr, costs -5.6%/yr.
- Metrics archive (`eval signals --metrics`, 4h, bracket `1.5:3:12`, both symbol sets, rules in `evals/preregistrations/2026_11_16_positioning_metrics.md`): `oi_supports_direction` and `oi_funding_divergence` over 5 years FAIL. SHORT `ls_crowding` (fired +0.083 / +0.065 R against a ~0.035 R fee) and SHORT `smart_vs_crowd` (+0.057 / +0.072 R) PASS, but not STRONG, since their lower bounds are below the fee. They are the first pre-registered passes. All LONG versions failed.

Rerun the command before relying on these numbers, since they describe one data window.
