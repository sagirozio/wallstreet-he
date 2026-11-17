# Daily content update — instructions for the scheduled run

Site: "וולסטריטר" (tagline: "השוק האמריקאי, בגובה העיניים"), a Hebrew site about the US stock market.
Repo: `sagirozio/wallstreet-he`. GitHub Pages serves `index.html` from `main`.
Everything the browser loads is generated: edit only `data.json` (content) and run `python3 scripts/build.py`.
The build writes `index.html`, `core.json`, `stocks.json`, `s/<T>.json`, `stock/<T>.html` (one Google-indexable page per stock) and `sitemap.xml`. Never edit those by hand. A GitHub Action also rebuilds them after every push, as a safety net.

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
  - Add 3–6 main `news` items plus as many stock items as you can (see §2 `news`; prepend; don't duplicate items already in the archive). Update `overview.brief` only if something big changed since the evening run; leave `reports`, `calendar`, `ipos` as they are unless there is clear new information.
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

- **Prepend** new items. Always fill `t` with the tickers the item is about (empty list for market/macro items): the stock pages show these items under "חדשות אחרונות" (the section is hidden for a stock with no item). Never delete or rewrite old items, because this is the news archive.
- **Two kinds of items:**
  - **Main items** (no `k` field): 3–6 per run, the biggest market and company stories. These appear on the home page and in the news strip.
  - **Stock items** (`"k":"stock"`): **cover as many individual stocks as possible on every run (morning, midday and evening) — aim for 20–40 per run, more if time allows.** Shown only on the stock page and in the news archive, not on the home page. Each one is about one company (`t` = one ticker), 1–2 Hebrew sentences with the concrete fact and numbers, from a source you retrieved.
- **Which stocks to cover, in this order** (only stocks that are on the site: cap >$1B, avg volume ≥500k — the ticker should appear in `data.json` under `themes`, `ytd` or `movers`, or have a `profiles` entry):
  1. every company that reported earnings since the last run (one stock item each, even if it also has a `reports` card);
  2. every stock in `movers.rows` and `movers.down` — find *why* it moved (results, guidance, deal, FDA, analyst action, offering);
  3. analyst upgrades/downgrades and price-target changes on stocks over ~$10B;
  4. deals, M&A, buybacks, offerings, guidance updates, regulatory/legal news, product launches, executive changes;
  5. the largest companies by cap (NVDA, AAPL, MSFT, GOOGL, AMZN, META, AVGO, TSLA, …) whenever they have any concrete news.
  Prefer a stock that has **no** item yet (or none in the last 30 days) over adding another item to one that does. Do one search per stock or per batch (e.g. "stock movers today", "analyst upgrades today", "premarket movers"), and never invent a reason for a move: if no source explains it, skip the stock.
- Item shape:

  ```json
  {"id":"YYYY-MM-DD-slug","date":"YYYY-MM-DD","t":["<tickers the item is about, e.g. NVDA>"],"tag":"<company or topic, short, Hebrew or brand name>","tone":"pos|neg|neu","title":"<Hebrew headline>","body":"<2–3 Hebrew sentences with numbers>","src":"<outlet name>","url":"<source URL>"}
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
- **Hebrew names for search:** if the company has a common Hebrew name (as Israeli media write it, e.g. אנבידיה, טבע) and it is missing from `scripts/he_names.json`, add it there (`"TICKER": "שם"`; extra spellings separated by spaces). The site search and the Google page title use it.
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
git add data.json index.html core.json stocks.json sitemap.xml stock.css s stock
git commit -m "Content update DD.MM (midday|morning|evening)"
git pull --rebase -X theirs origin main                # the data bots may have pushed meanwhile
python3 scripts/build.py && git add index.html core.json stocks.json sitemap.xml stock.css s stock && (git diff --cached --quiet || git commit -m "Rebuild site files")
git push origin HEAD:main                              # if rejected: repeat the last three lines
```

End the commit message with the attribution lines your environment requires.

If the push is rejected, pull again with `--rebase` and retry once.

## 5. Report

Finish with a short Hebrew summary for the owner. Cover:

- what was added: brief, N main news items, N stock items (how many distinct tickers), which reports;
- anything skipped and why;
- the site link: https://sagirozio.github.io/wallstreet-he/
