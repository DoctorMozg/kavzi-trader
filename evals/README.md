# Evaluation suite

Four commands under `kavzitrader eval` (`kavzi_trader/cli/commands/evals.py`):

| Command | Calls an LLM? | Purpose |
| --- | --- | --- |
| `build-dataset` | no | Download candles, write the frozen triple-barrier cases |
| `run` | **yes, paid** | Push cases through Scout, Analyst and Trader |
| `report` | no | Score a finished run |
| `signals` | no | Measure whether each live confluence signal predicts outcomes |

All of them read candles from the gitignored cache `data/eval_cache/` (`--cache-dir`). Candle and funding history can always be re-downloaded from Binance. Open interest older than about 30 days cannot, so don't delete the OI files.

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

No LLM calls. Asks whether each live confluence signal predicts outcomes, before any LLM sees the setup. It samples every Nth cached 15m bar, computes indicators with the live calculator over the trailing history window, and gets flags from the live `ConfluenceCalculator`. Each bar is labelled with every `--bracket SL_ATR:TP_ATR:HORIZON_BARS` (repeatable, default `1.5:3:96`).

Per signal and side, the report (`results/evals/signals_<UTC time>.md`, override with `--out`) gives:

- how often it fires
- mean R when fired and when not fired
- **lift**: fired minus not-fired mean R. This cancels market drift, so the verdict uses lift, not raw mean R
- a 95% interval, widened by sqrt(horizon / stride) because neighbouring samples share outcome windows. A signal counts as having edge only when |lift| exceeds that interval
- win rate and score buckets
- the taker round-trip fee in R, from `paper.commission_rate`. Lift has to clear this to be tradable

Options:

- `--stride N` (default 17): keep it coprime with 96, the bars per day. A stride of 16 sampled the same 6 times of day and biased the volume signals (above-average-volume rate swung 27% to 43% by phase).
- `--funding`: downloads Binance funding history (public endpoint, no key) and scores the live funding signal: z-score of the latest settlement over the last 100 settlements, as live.
- `--oi` (implies `--funding`): downloads 15m open interest and scores `oi_supports_direction` and `oi_funding_divergence` through the live `OrderFlowCalculator`. Binance serves only about the last 30 days of OI, so only bars inside that window, with a full 24h of OI history, are sampled. Use a small stride such as 5. The cache keeps old rows, so running this at least monthly builds a longer history. Refresh candles with `build-dataset` too, or new bars won't be sampled.

Cache files in `data/eval_cache/`: `<SYMBOL>_15m.csv.gz`, `<SYMBOL>_funding.csv.gz`, `<SYMBOL>_oi_15m.csv.gz`.

### What we found (snapshot, 2026-11-15)

- 12 months x 8 symbols, six brackets: no candle or funding signal showed lift above chance. 3 of 60 candle tests passed, about what chance gives at 95%.
- The largest lifts (+0.05 to +0.07 R) were far below the 0.15 to 0.30 R round-trip fee.
- 27 days of OI: `oi_supports_direction` leaned positive (+0.04 to +0.14 R) but was not significant and still below the fee.
- Implication: loosening the Scout or Analyst gates would trade noise. A new feature should show lift above the fee in `eval signals` first.

Rerun the command before relying on these numbers, since they describe one data window.
