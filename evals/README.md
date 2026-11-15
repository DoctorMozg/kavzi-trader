# Evaluation suite

Five commands under `kavzitrader eval` (`kavzi_trader/cli/commands/evals.py`):

| Command | Calls an LLM? | Purpose |
| --- | --- | --- |
| `build-dataset` | no | Download candles, write the frozen triple-barrier cases |
| `run` | **yes, paid** | Push cases through Scout, Analyst and Trader |
| `report` | no | Score a finished run |
| `signals` | no | Measure whether each live confluence signal predicts outcomes |
| `refresh-cache` | no | Fill cached candles, funding and OI up to today 00:00 UTC, leave `cases_v1.jsonl` alone |

They share the gitignored cache `data/eval_cache/` (`--cache-dir`): `build-dataset` and `refresh-cache` download into it, the other commands read from it. Candle and funding history can always be re-downloaded from Binance. Open interest older than about 30 days cannot, so don't delete the OI files.

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

## Signal edge

    uv run kavzitrader eval signals
    uv run kavzitrader eval signals --bracket 1.5:3:96 --bracket 1:2:48 --funding
    uv run kavzitrader eval signals --oi --stride 5
    uv run kavzitrader eval refresh-cache --interval 4h --months 60
    uv run kavzitrader eval signals --interval 4h --stride 1 --candidates --bracket 1:2:6 --bracket 1.5:3:12

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
- `--oi` (implies `--funding`): downloads open interest (15m at the 15m interval, see below) and scores `oi_supports_direction` and `oi_funding_divergence` through the live `OrderFlowCalculator`. Binance serves only about the last 30 days of OI, so only bars inside that window, with a full 24h of OI history, are sampled. Use a small stride such as 5. The cache keeps old rows, so running `eval refresh-cache` monthly grows the OI history past Binance's ~30-day limit and adds the new candles, without which new bars won't be sampled.

### Refreshing the cache

    uv run kavzitrader eval refresh-cache --interval 4h --months 60

No LLM calls. Options: `--interval` (default: trading interval), `--months` (default 12), `--cache-dir`. Fills candles, funding and OI up to today 00:00 UTC and never touches `cases_v1.jsonl`. Reruns fetch only the missing head or tail. OI uses the largest openInterestHist period that doesn't exceed the interval, capped at 30m, so 1h and 4h use `oi_30m`. It prints one line per symbol with candle count, date range, funding rows and OI rows.

`scripts/refresh_eval_cache.sh` refreshes 15m, 1h and 4h in one go and logs to `results/logs/refresh_eval_cache_<date>.log`. Run it at least monthly, or OI older than Binance's ~30 days is lost. A crontab line for the 1st of each month at 03:00:

    0 3 1 * * /path/to/kavzitrader/scripts/refresh_eval_cache.sh

Cache files in `data/eval_cache/`: `<SYMBOL>_15m.csv.gz` (and `<SYMBOL>_<interval>.csv.gz` for other intervals), `<SYMBOL>_funding.csv.gz`, `<SYMBOL>_oi_15m.csv.gz`, `<SYMBOL>_oi_30m.csv.gz`.

### What we found (snapshot, 2026-11-15)

- 12 months x 8 symbols, six brackets: no candle or funding signal showed lift above chance. 3 of 60 candle tests passed, about what chance gives at 95%.
- The largest lifts (+0.05 to +0.07 R) were far below the 0.15 to 0.30 R round-trip fee.
- 27 days of OI: `oi_supports_direction` leaned positive (+0.04 to +0.14 R) but was not significant and still below the fee.
- Candidates on 15m (12 months, six brackets): none beat the fee. `taker_flow` lift was negative (-0.04 to -0.08 R, significant in 4 cells), so heavy taker buying or selling slightly reverses, still far below the 0.15 to 0.29 R fee. `htf_trend` LONG was +0.06 R in one cell. `btc_lead` showed nothing.
- Longer timeframes cut the fee in R: about 0.07 to 0.14 R at 1h and 0.03 to 0.07 R at 4h. 1h, 12 months: no signal with positive lift (two negative cells).
- 4h, 12 months: `ema_alignment` lift was positive in all 8 side and bracket cells (+0.04 to +0.23 R). Over 5 years (79k bars) it shrank to +0.01 to +0.05 R and was not significant, so the 12-month result was mostly one regime.
- 4h, 5 years: `taker_flow` LONG lift was +0.04 to +0.075 R in all 4 brackets, above the fee in two, but only 2 of 104 tests passed, fewer than chance predicts. It is a lead to check out of sample (for example per year), not an edge.
- Implication: loosening the Scout or Analyst gates would trade noise. A new feature should show lift above the fee in `eval signals` first.

Rerun the command before relying on these numbers, since they describe one data window.
