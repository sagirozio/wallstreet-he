#!/usr/bin/env bash
# Hourly (started in the background by loop.py): fresh Finnhub headlines + same-day earnings cards, committed to main.
# Works in its own clone so the loop's working copy (intraday tables, not committed) stays separate.
set -u
D=$(mktemp -d)
git clone -q --depth 30 "https://x-access-token:${GH_TOKEN}@github.com/${GITHUB_REPOSITORY:-sagirozio/wallstreet-he}.git" "$D" || exit 1
cd "$D"
timeout 2400 python scripts/finnhub_news.py || true
timeout 300 python scripts/finnhub_today.py || true
bash scripts/commit.sh "Stock headlines + same-day earnings cards (Finnhub, hourly)" news_src.json data.json
