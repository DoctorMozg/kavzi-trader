#!/usr/bin/env bash
# Extends the eval candle, funding and OI caches up to today. Run it monthly:
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
echo "== $(date -u +%FT%TZ) done" >>"$log"
