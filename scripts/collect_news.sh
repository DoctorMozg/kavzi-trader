#!/usr/bin/env bash
# Archives crypto headlines from outlet RSS feeds. Run hourly: the feeds keep
# only 1-4 days of items, so a missed day loses headlines for good.
set -euo pipefail

cd "$(dirname "$0")/.."
# cron/systemd start with a minimal PATH; uv installs to ~/.local/bin by default.
export PATH="$HOME/.local/bin:$PATH"

log_dir=results/logs
mkdir -p "$log_dir"
log="$log_dir/collect_news_$(date -u +%Y%m).log"
echo "== $(date -u +%FT%TZ) collect" >>"$log"
uv run kavzitrader news collect >>"$log" 2>&1
