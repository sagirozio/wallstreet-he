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
- Update `strip` items only with values you verified. Otherwise leave them.
- `market` ("מצב השוק" section) — **update on every evening run** (and the morning run if the last close isn't there yet):
  `{"note": "<one Hebrew sentence: which close this is, e.g. סגירה ביום שני, 16.11.2026, and the main takeaway>", "idx": [{"k":"S&P 500","v":"7,416.59","d":-1.92,"w":<optional weekly % on Fridays>}, {"k":"נאסד״ק",...}, {"k":"דאו ג׳ונס",...}, {"k":"ראסל 2000",...}]}`
- `vix`: `{"v": <close>, "c": <daily %>, "week": <% vs last Friday close>, "from": <last Friday close>, "note": "<short Hebrew>"}` — update together with `market`.
- Never edit the index cards inside `template.html`; they are rendered from `overview.market`.

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

`profiles` holds the stock profile pages ("תעודת זהות", at `#stock/TICKER`):
`{"TICKER": {"desc": "<one Hebrew sentence>", "about": "<Hebrew paragraph(s)>"}}`.

- **`desc`** — one short sentence: what the company does (shown at the top of the page).
- **`about`** — the deeper "על החברה" section: 4–6 Hebrew sentences, optionally two paragraphs separated by `\n`. Cover:
  what the company sells and to whom; its main segments or products (with the biggest revenue sources if known);
  where it operates; its position in its industry (e.g. one of the largest X, key competitors); and one notable
  recent fact (a big acquisition, spin-off, new product line) only if you retrieved it.
- **Source material:** `about_src.json` (filled daily by a GitHub workflow) has Yahoo's English business summary
  per ticker. Use it as research, together with what you search. **Never copy or translate it sentence by sentence** —
  write your own Hebrew text. `about_src.json` is not shown on the site; do not edit it.
- Per run: write `about` (and `desc` if missing) for up to **80 stocks** that don't have `about` yet.
- Priority order:
  1. companies in new report cards;
  2. this week's `calendar`;
  3. stocks named in today's news;
  4. the top of `ytd`, `movers` and the November gainers;
  5. then the rest of `themes.stocks`, largest market cap first.
- Only write what you are confident about. If unsure about a small company and `about_src.json` has nothing, skip it.
- Factual and neutral: business lines, products, customers, markets. No opinions, valuations or recommendations.
- Never change an existing `desc`/`about` unless it is factually wrong or outdated.
- Facts like headquarters, employees and website come automatically from `data.json["facts"]` — don't repeat them in `about`.

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
