# Daily content update — instructions for the scheduled run

Site: "וולסטריטר" (tagline: "השוק האמריקאי, בגובה העיניים"), a Hebrew site about the US stock market.
Repo: `sagirozio/wallstreet-he`. GitHub Pages serves `index.html` from `main`.
`index.html` is generated: edit `data.json` (content) and run `python3 scripts/build.py`.

**Never edit by hand:** `sectors`, `themes`, `breadth`, `ytd` in `data.json`.
The nightly GitHub Action recomputes them from Yahoo Finance.

## 0. Setup

1. Attach the repo with push access. Clone it with `git clone --depth 5 https://github.com/sagirozio/wallstreet-he`.
2. Work in Israel time (Asia/Jerusalem). US market hours are 16:30–23:00 Israel time.
3. Note which run this is:
   - **midday:** around 11:00 (news-only run).
   - **morning:** before 16:30.
   - **evening:** after 23:00.

## 1. Research (WebSearch / WebFetch)

Search separately for each item below. Use only what you retrieved, never memory.

- **Midday run (11:00, news only):**
  - Stories since the evening run that matter for US stocks: overnight company news, Asia and Europe session, US futures, notable pre-market announcements (deals, guidance, analyst moves on big names, regulation).
  - Add 3–6 new `news` items (prepend; don't duplicate items already in the archive). Update `overview.brief` only if something big changed since the evening run; leave `reports`, `calendar`, `ipos` as they are unless there is clear new information.
  - Profiles: still add descriptions as in §2 `profiles`.
  - Commit message: `Content update DD.MM (midday)`.
- **Morning run:**
  - US stock futures, Asia and Europe overnight.
  - The 3–6 biggest US stock stories of the last 24h.
  - Earnings released since the previous run: yesterday after close, and this morning before open.
  - Today's macro events.
- **Evening run:**
  - How the session closed: S&P 500, Nasdaq, Dow and Russell 2000, with % moves.
  - The day's biggest stock stories.
  - Earnings released after today's close.
- **Monday morning run:** also refresh `calendar`, the week's most anticipated earnings from earningswhispers.com/calendar (see §2).

Only companies with market cap above $1B, on every part of the site.

Prefer primary sources: company press releases, IR pages, SEC filings, and Reuters, CNBC or AP.

For earnings, cross-check actual vs. consensus in at least 2 sources.
If the sources conflict and you cannot resolve it, leave the company out and say so in your final report.

## 2. Edit `data.json`

Read the existing entries first and copy their exact shape.

### `overview` (every run)

- `brief`: 4–6 Hebrew sentences, "השוק ב-30 שניות". Short and factual, with numbers.
- `asOf`: `"DD.MM.YYYY · HH:MM"`, Israel time.
- `rev`: `YYYYMMDDHHMM` as a number. It must be higher than the current value.
- Update `strip` items, and the index cards in `template.html` if you edit those, only with values you verified. Otherwise leave them.

### `news` (every run)

- **Prepend** 3–6 new items. Never delete or rewrite old items, because this is the news archive.
- Item shape:

  ```json
  {"id":"YYYY-MM-DD-slug","date":"YYYY-MM-DD","tag":"<company or topic, short, Hebrew or brand name>","tone":"pos|neg|neu","title":"<Hebrew headline>","body":"<2–3 Hebrew sentences with numbers>","src":"<outlet name>","url":"<source URL>"}
  ```

- Skip a story already covered: check recent titles and ids.

### `reports` (when companies reported)

- **One card per report.** Add a card for each company >$1B that reported since the last run and that investors care about. This means big names, or companies on this week's `calendar`.
- **Fields:** follow the existing cards exactly.
  - id `TICKER-YYYY-MM`, plus `t`, `co`, `sector` (Hebrew, as used by existing cards) and `date`.
  - `q`, `epsAct`, `epsEst`, `epsYoy` (number in %), `epsBasis`.
  - `revAct`, `revEst` (in $B), `revYoy`.
  - `guide` (`raised|above|inline|below|given|none`), `guideText`, `note`, `react`, `hook`.
  - `ir`: a working IR or press-release URL. Verify it opens.
- **`epsYoy` is always a number.** Compare to the same quarter last year, on the same basis: GAAP vs GAAP, or adjusted vs adjusted.
- **Do not duplicate:** if the id exists, update it instead.

### `calendar` (Monday morning, or when clearly stale)

- **`days`:** 5 entries, Mon–Fri. Each has `d` ("שני 16.11"), `econ` (macro note or ""), and `items`.
- **Item shape:** `{t, co, time:"bmo"|"amc", star:false, eps?, rev?, at?, n?, il?}`.
- **Include** only the "Most Anticipated" names from Earnings Whispers, with market cap above $1B.
- **Mark** Israeli companies with `"il":true`.
- **`rev`:** bump `calendar.rev` (YYYYMMDDHHMM).
- **`week`:** set it, e.g. `"16–20.11"`.

### `profiles` (every run)

`profiles` holds the stock profile pages ("תעודת זהות", at `#stock/TICKER`): `{"TICKER": {"desc": "<one or two Hebrew sentences: what the company does>"}}`.

- Add a Hebrew `desc` (one sentence) for up to 80 stocks per run that don't have one yet. The goal is that every stock in `themes.stocks` and `reports` gets one; until then the page shows an automatic fallback ("X היא חברה בתחום … בסקטור …").
- Priority order:
  1. companies in new report cards;
  2. this week's `calendar`;
  3. stocks named in today's news;
  4. the top of `ytd`, `movers` and the November gainers;
  5. then the rest of `themes.stocks`, largest market cap first.
- Only write what you are confident about. If unsure what a small company does, skip it and leave the fallback.
- Keep it factual and neutral: business lines, main products and customers. No opinions or valuations.
- Never change an existing `desc` unless it is factually wrong.

### `ipos` (when there is news)

Update `items` when an IPO is priced or listed, or a big filing happens. Shape: as existing.

## 3. Rules

- **Facts only.** Never write buy/sell/hold recommendations, price targets of your own, or predictions. Quoting what an analyst or bank said is fine, with attribution.
- **Hebrew style:** plain, short sentences, numbers with % and $. English names for companies and tickers.
- **No invented data.** If a number is not in a source you retrieved, leave it out.
- **Copyright:** paraphrase, no quotes longer than a few words.
- **Anthropic:** when writing about Anthropic (e.g. its IPO), stay neutral and factual.

## 4. Build, check, publish

```bash
python3 -c "import json;json.load(open('data.json'))"   # must not fail
python3 scripts/build.py
git pull --rebase origin main                          # the nightly bot may have pushed
git add data.json index.html template.html
git commit -m "Content update DD.MM (midday|morning|evening)"
git push origin HEAD:main
```

End the commit message with the attribution lines your environment requires.

If the push is rejected, pull again with `--rebase` and retry once.

## 5. Report

Finish with a short Hebrew summary for the owner. Cover:

- what was added: brief, N news items, which reports;
- anything skipped and why;
- the site link: https://sagirozio.github.io/wallstreet-he/
