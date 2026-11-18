# Content runs — instructions

Site "וולסטריטר" (Hebrew, US stock market). Repo `sagirozio/wallstreet-he`, served by GitHub Pages from `main`.
Edit only `data.json` (and `scripts/he_names.json`), then build. Everything else is generated or automatic.

**Automatic — never touch:** `analysts.json`, `earnhist.json`, `screen.json`, `themes.x` (mktx.py: sparklines, rank changes, sector breadth), RS ratings (build.py), prices, `sectors`, `themes`, `breadth`, `ytd`, `gainers`, `movers`, `premarket`, `calendar` list,

**Banned source: Al Jazeera.** Never use aljazeera.com / Al Jazeera (any language) as a source, link or attribution: not for news items, the brief, report cards or anything else. If a story appears only there, find it on another reliable outlet or skip it.
`insiders`, `recap`, basic earnings cards (`"auto": true`), facts. Raw English headlines per stock: `news_src.json` (research only).

## Your job, in this order (stop when time runs out; the rest waits for the next run)

| Run | When (Israel) | Do |
|---|---|---|
| hourly | :52, 13:52–22:52 | news (3–8 items) + rewrite `overview.brief` |
| midday | 10:39 | news (main 3–6 + stock 20–40) |
| morning | 15:13 | brief, news, cards for today's reporters, enrich cards, profiles |
| evening | 23:47 | brief + `market` + `vix`, news, cards for after-close reporters, enrich cards, profiles |

1. `overview.brief` · 2. main news · 3. report cards of today's big reporters · 4. stock news · 5. enrich `auto` cards (≥15, largest first) · 6. `profiles` · 7. `calendar` notes, `ipos`.

## Research

Search per item; use only what you retrieved. Primary sources first (press release, IR, SEC, Reuters/CNBC/AP).
Earnings: actual vs consensus from 2 sources; if they conflict, skip and say so. Only companies above $1B.
Never invent a reason for a move — no source, no explanation.

## data.json — shapes

**`overview`**
- `brief`: 3–5 × `{"h": "<≤8 words>", "t": "<one sentence with numbers>", "tone": "pos|neg|neu"}`. First item = the market now
  (close / futures / session). No index % (the line above is live). Earnings only for significant companies (~$50B+, or a 10%+ move).
- `asOf` `"DD.MM.YYYY · HH:MM"` (Israel), `rev` `YYYYMMDDHHMM` (number, higher than before).
- Evening: `market` `{"note", "idx":[{"k":"S&P 500","v":"7,416.59","d":-1.92}, נאסד״ק, דאו ג׳ונס, ראסל 2000]}` and
  `vix` `{"v","c","week","from","note"}`. Macro labels keep the indicator name (CPI, PPI, PCE, ריבית…).

**`news`** — prepend; never edit or delete old items (archive). No duplicates (check today's titles and tickers).
`{"id":"YYYY-MM-DD-slug","date":"YYYY-MM-DD","t":["NVDA"],"tag":"…","tone":"pos|neg|neu","title":"<Hebrew>","body":"<1–3 sentences, numbers>","src":"…","url":"…"}`
- Main items: no `k`. Stock items: `"k":"stock"`, one ticker, cover as many different stocks as possible.
- Stock priority: today's reporters → `movers` (why) → analyst actions on $10B+ → deals/guidance/legal/execs → mega caps.
  Prefer stocks without a recent item. Start from `news_src.json`, confirm in the article, write in your own Hebrew.

**`reports`** — one card per report, id `TICKER-YYYY-MM` (update if it exists). Copy an existing card's fields:
`t co sector date q epsAct epsEst epsYoy epsBasis revAct revEst revYoy guide guideText note react hook ir`.
`revAct`/`revEst` in $B; `epsYoy` a number, same basis as last year; `guide` = raised|above|inline|below|given|none.
Enrich `auto` cards: add `revEst`, guidance, `note`, `hook`, fix numbers, then delete `auto` (and `src`).
For significant reporters (~$50B+ or a 10%+ move) also add research fields: `call` = 2–4 short Hebrew bullets of what management said about demand, guidance and risks (array of strings; sourced, paraphrased). Take them from the earnings call when there is one; many companies hold no call (e.g. Berkshire Hathaway, most foreign filers) — then use the press release, shareholder letter or prepared remarks, and if there is nothing reliable, leave the field out, and `delta` = one sentence on what changed versus last quarter (guidance raised/cut, trend change). The site shows last quarter's `guideText` next to the new one automatically.

**`profiles`** — `{"T": {"desc": "<one sentence>", "about": "<4–6 sentences>"}}` for stocks without `about`, up to 80 per run
(order: new cards → calendar → today's news → movers/ytd → largest caps). Research from `about_src.json` + search; never translate it line by line.
Missing Hebrew company name → add to `scripts/he_names.json`.

**`calendar`** — list is automatic. Add only `n` (one Hebrew line) on notable items, `econ` per day, `at` when known.
**`ipos`** — when something is priced/listed/filed. Same shape as existing.

## Rules

Facts only; no recommendations, targets or predictions (quoting an analyst with attribution is fine). Plain short Hebrew,
English company names. No number without a source. Paraphrase, no long quotes. Neutral wording about Anthropic.

## Build and publish

```bash
python3 -c "import json;json.load(open('data.json'))"
bash scripts/commit.sh "Content update DD.MM (hourly|midday|morning|evening)" data.json scripts/he_names.json
```
`commit.sh` builds, commits, rebases on the bots' pushes and retries. End commit messages with the attribution your environment requires.

## Report

Short Hebrew summary: brief changed?, N main + N stock items (distinct tickers), cards added/enriched, profiles, anything skipped and why.
