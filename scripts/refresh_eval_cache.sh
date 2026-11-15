#!/usr/bin/env bash
# Extends the eval candle, funding and OI caches up to today. Run it weekly:
# Binance serves only ~30 days of OI, so older OI exists only in this cache.
set -euo pipefail

cd "$(dirname "$0")/.."
# cron starts with a minimal PATH; uv installs to ~/.local/bin by default.
export PATH="$HOME/.local/bin:$PATH"

log_dir=results/logs
mkdir -p "$log_dir"
log="$log_dir/refresh_eval_cache_$(date -u +%Y%m%d).log"

for interval in 15m 1h 4h; do
    echo "== $(date -u +%FT%TZ) refresh $interval" >>"$log"
    uv run kavzitrader eval refresh-cache --interval "$interval" >>"$log" 2>&1
done
# Extra symbols for the forward test in evals/preregistrations/.
holdout=DOGEUSDT,LTCUSDT,DOTUSDT,BCHUSDT,ATOMUSDT,TRXUSDT,ETCUSDT,FILUSDT
echo "== $(date -u +%FT%TZ) refresh 4h holdout" >>"$log"
uv run kavzitrader eval refresh-cache --interval 4h --symbols "$holdout" >>"$log" 2>&1
echo "== $(date -u +%FT%TZ) done" >>"$log"
