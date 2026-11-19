#!/usr/bin/env bash
# Commit + push from GitHub Actions, safely alongside other jobs and the scheduled content runs.
# usage: scripts/commit.sh "message" [own files...]
# Own files are committed first; the derived site files are rebuilt on top of the latest main before pushing.
set -u
PY=$(command -v python3 || command -v python)
msg="$1"; shift
git config user.name "wallstreet-bot"
git config user.email "bot@users.noreply.github.com"
DERIVED="index.html core.json breadth.json news.json screen.json ins news_times.json reports.json stocks.json sitemap.xml stock.css s stock"
"$PY" scripts/build.py >/dev/null
# guard: never publish a page whose script does not parse (one syntax error blanks the whole site)
if command -v node >/dev/null 2>&1; then
  node -e "const s=require('fs').readFileSync('index.html','utf8');const m=[...s.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(x=>x[1]).join('\n');try{new Function(m)}catch(e){console.error('index.html script error: '+e.message);process.exit(1)}" || { echo "ABORT: script error in index.html, nothing committed"; exit 1; }
fi
git add "$@" $DERIVED
git diff --cached --quiet && { echo "nothing to commit"; exit 0; }
git commit -q -m "$msg"
for i in 1 2 3 4 5; do
  if git pull -q --rebase -X theirs origin main; then
    "$PY" scripts/build.py >/dev/null && git add $DERIVED && { git diff --cached --quiet || git commit -q -m "Rebuild site files"; }
    git push -q && { echo "pushed"; exit 0; }
  else
    git rebase --abort 2>/dev/null
  fi
  sleep $((i * 8))
done
echo "push failed"; exit 1
