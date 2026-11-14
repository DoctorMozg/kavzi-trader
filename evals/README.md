# Evaluation dataset

`cases_v1.jsonl` holds 200 frozen triple-barrier cases (balanced LONG / SHORT / NO_TRADE) over the configured futures symbols at 15m. Candle arrays are not stored; they live in the gitignored cache `data/eval_cache/` and can be re-downloaded because Binance history is immutable.

Rebuild the cache and the dataset (public market data, no API keys):

    uv run kavzitrader eval build-dataset --months 12 --cases 200 --seed 42 --end-date YYYY-MM-DD

Pass the same `--end-date` as in each record's `generator.data_end_ms` to reproduce a dataset exactly; downloads are resumable and a rerun only fetches missing candles.

Labels: entry is the close of the decision candle. Both a LONG and a SHORT bracket are walked over the next 24h of highs and lows. The stop is 1.25x ATR (LOW/NORMAL) or 1.5x ATR (HIGH/EXTREME) with the target from the bot's ATR_2X geometry (min R:R 2). A bar that touches both SL and TP counts as SL. LONG or SHORT means only that side hit its TP first; if both hit TP, the earlier one wins and a same-bar tie is NO_TRADE; anything else is NO_TRADE.
