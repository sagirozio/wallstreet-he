#!/usr/bin/env bash
# Commit + push from GitHub Actions, safely alongside other jobs and the scheduled content runs.
# usage: scripts/commit.sh "message" [own files...]
# Own files are committed first; the derived site files are rebuilt on top of the latest main before pushing.
set -u
msg="$1"; shift
git config user.name "wallstreet-bot"
git config user.email "bot@users.noreply.github.com"
DERIVED="index.html core.json breadth.json insiders.json news_times.json reports.json stocks.json sitemap.xml stock.css s stock"
python scripts/build.py >/dev/null
git add "$@" $DERIVED
git diff --cached --quiet && { echo "nothing to commit"; exit 0; }
git commit -q -m "$msg"
for i in 1 2 3 4 5; do
  if git pull -q --rebase -X theirs origin main; then
    python scripts/build.py >/dev/null && git add $DERIVED && { git diff --cached --quiet || git commit -q -m "Rebuild site files"; }
    git push -q && { echo "pushed"; exit 0; }
  else
    git rebase --abort 2>/dev/null
  fi
  sleep $((i * 8))
done
echo "push failed"; exit 1
