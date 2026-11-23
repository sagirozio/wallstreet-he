"""Builds the site from template.html + data.json (+ facts.json).

data.json stays the single source of truth (scripts and the scheduled content runs edit it).
This script derives everything the browser loads:
  index.html   – the app, with the light "core" data inlined (no profiles / per-stock lists)
  core.json    – the same core data, polled by the page every 5 minutes
  stocks.json  – the full stock universe (industry lists, exchanges, Hebrew names), loaded once in the background
  s/T.json     – per-stock details (profile, facts, next earnings date), loaded when a stock page opens
  stock/T.html – a static, indexable page per stock (for Google), linking into the app
  sitemap.xml
Files are only rewritten when their content changes, to keep git history small.
"""
import json, os, pathlib, re, html

root = pathlib.Path(__file__).resolve().parent.parent
SITE = "https://wallstreeter.co.il/"

def load(p, default=None):
    p = root / p
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default

def write(rel, text):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists() and p.read_text(encoding="utf-8") == text:
        return False
    p.write_text(text, encoding="utf-8")
    return True

def js(o):
    return json.dumps(o, ensure_ascii=False, separators=(",", ":"))

data = load("data.json")
facts = load("facts.json", {}) or {}
earndates = (load("earndates.json", {}) or {}).get("d", {})   # past report days (the session that reacted), newest first
he_names = load("scripts/he_names.json", {}) or {}
themes = data.get("themes") or {}
stocks = themes.get("stocks") or {}
exch = themes.get("ex") or {}
profiles = data.get("profiles") or {}
earn = data.get("earnDates") or {}
reports = data.get("reports") or []
news = data.get("news") or []
# publication time of each news item: the first build that saw it (Israel time), kept in news_times.json
import datetime as _dtn, zoneinfo as _zi
_ntp = root / "news_times.json"
try: _nt = json.loads(_ntp.read_text(encoding="utf-8"))
except Exception: _nt = None   # first run: items already there get no time (unknown)
_now = _dtn.datetime.now(_zi.ZoneInfo("Asia/Jerusalem"))
_first = _nt is None; _nt = _nt or {}
for _n in news:
    _k = (_n.get("date") or "") + "|" + (_n.get("title") or "")
    # US-dated items written after midnight Israel time still count as new (date = yesterday)
    _recent = _n.get("date") in (_now.strftime("%Y-%m-%d"), (_now - _dtn.timedelta(days=1)).strftime("%Y-%m-%d"))
    if _k not in _nt: _nt[_k] = _now.strftime("%Y-%m-%d %H:%M") if not _first and _recent else ""
    if _nt[_k]:
        try: _gap = (_dtn.date.fromisoformat(_nt[_k][:10]) - _dtn.date.fromisoformat(_n.get("date") or "")).days
        except ValueError: _gap = 9
        if 0 <= _gap <= 1:
            if not _n.get("time"): _n["time"] = _nt[_k][11:]
            if _gap: _n["tday"] = _nt[_k][:10]   # Israel date of that time (the item's own date is the US one)
_keep = {(_n.get("date") or "") + "|" + (_n.get("title") or "") for _n in news}
_nt = {k: v for k, v in _nt.items() if k in _keep}

# ---------- RS rating (relative strength, 1-99): a weighted 12-month performance, placed against the S&P 500 stocks ----------
# IBD-style weighting: the last 3 months count double. score = 0.4*3M + 0.2*6M + 0.2*9M + 0.2*12M (9M is estimated as the 6M/12M average)
def _rs_score(r):
    if not isinstance(r, dict): return None
    q, h, y = r.get("q"), r.get("h"), r.get("y")
    if q is None or h is None or y is None: return None
    return 0.4 * q + 0.2 * h + 0.2 * (h + y) / 2 + 0.2 * y
# The rating is measured against the S&P 500: RS 90 = a stronger score than 90% of the S&P 500 stocks.
import bisect as _bis
_spx = {t_ for l_ in ((data.get("sectors") or {}).get("mem") or {}).values() for t_ in l_}
_ref = sorted(x for x in (_rs_score(s_[3]) for l_ in stocks.values() for s_ in l_ if s_[0] in _spx and len(s_) > 3) if x is not None)
def _rs_set(score, obj):
    if score is None or len(_ref) < 100: return
    obj["rs"] = max(1, min(99, round(_bis.bisect_left(_ref, score) / len(_ref) * 99)))
for l_ in stocks.values():
    for s_ in l_:
        if len(s_) > 3 and isinstance(s_[3], dict): _rs_set(_rs_score(s_[3]), s_[3])
for r_ in themes.get("rows", []):
    if len(stocks.get(r_.get("en"), [])) >= 3: _rs_set(_rs_score(r_), r_)
# sectors: the sector's own returns against the same S&P 500 stocks (kept in themes.secRs: the intraday sector table replaces the rows)
themes["secRs"] = {}
for r_ in (data.get("sectors") or {}).get("rows", []):
    o_ = {}; _rs_set(_rs_score(r_), o_)
    if "rs" in o_ and r_.get("t"): themes["secRs"][r_["t"]] = o_["rs"]

universe = {}                       # T -> (co, cap, industry)
for ind, lst in stocks.items():
    for s in lst:
        universe[s[0]] = (s[1], s[2], ind)

# ---------- core (inlined + polled) ----------
core = {k: v for k, v in data.items() if k not in ("profiles", "earnDates", "hl52", "insiders", "premkt")}
# insider trades: own file, loaded by the stock page and the insiders section

# reports: the page carries only the last 3 weeks; the full archive is reports.json (loaded on demand)
import datetime as _dt
_cut = (_dt.date.today() - _dt.timedelta(days=4)).isoformat()
core["reports"] = [r for r in reports if str(r.get("date", "")) >= _cut]
core["reportsN"] = len(reports)
write("reports.json", js(reports))
core["themes"] = {k: v for k, v in themes.items() if k not in ("stocks", "ex")}
core["themes"]["n"] = len(universe)
# breadth: the per-day stock lists go to breadth.json (loaded when the breadth section opens)
_b = core.get("breadth") or {}
write("breadth.json", js({"rows": [{"d": r.get("d"), "L": r.get("L")} for r in _b.get("rows", []) if r.get("L")]}))
core["breadth"] = {**_b, "rows": [{k: v for k, v in r.items() if k != "L"} for r in _b.get("rows", [])]}
write("news_times.json", json.dumps(_nt, ensure_ascii=False, indent=0, sort_keys=True))
# news: the page carries the last 3 days; the full archive is news.json (news page, stock pages)
_ncut = (_dt.date.today() - _dt.timedelta(days=3)).isoformat()
write("news.json", js(news))
core["news"] = [n for n in news if str(n.get("date", "")) >= _ncut][:80]
core["newsN"] = len(news)
core["news0"] = min((n.get("date") for n in news if n.get("date")), default="")   # first day of the news archive (timeline on stock pages)
# insider trades: one small file per stock (ins/<T>.json) instead of one big file
import os as _os
_ins = (data.get("insiders") or {}).get("rows", [])
_by = {}
for _r in _ins: _by.setdefault(_r["t"], []).append({k: _r[k] for k in ("who", "role", "type", "val", "date", "plan", "url")})
(root / "ins").mkdir(exist_ok=True)
for _f in (root / "ins").glob("*.json"):
    if _f.stem not in _by: _f.unlink()
for _t, _l in _by.items():
    if re.fullmatch(r"[A-Z0-9.\-]{1,10}", _t): write(f"ins/{_t}.json", js(_l))
if (root / "insiders.json").exists(): (root / "insiders.json").unlink()
# industries: number of member stocks on each row (the table ranks only groups with 3+ stocks)
_th = core.get("themes") or {}
_stk = (data.get("themes") or {}).get("stocks") or {}
if _th.get("rows"): _th["rows"] = [{**r, "cnt": len(_stk.get(r.get("en"), []))} for r in _th["rows"]]
core_txt = js(core)
write("core.json", core_txt)
# ---- S&P 500 earnings, quarter by quarter (spxe.json, market page): the net income of the current members from their SEC filings (fund/),
# summed over 12 months. A company's fiscal quarter counts in the calendar quarter that holds most of it (a quarter ending in Jan / Apr / Jul / Oct
# goes to the quarter before, one ending in Feb / May / Aug / Nov to the quarter after). Only companies with every quarter of the range are
# summed, so a company with missing filings does not make a jump. The page compares it in % with the index itself (SPY).
def _cq(d):
    y, m = int(d[:4]), int(d[5:7])
    if int(d[8:10]) <= 7: m -= 1                       # a period ending in the first days of a month belongs to the month before
    if m == 0: y, m = y - 1, 12
    r = m % 3
    if r == 1: m -= 1                                  # Jan / Apr / Jul / Oct -> the quarter before
    elif r == 2: m += 1                                # Feb / May / Aug / Nov -> the quarter after
    if m == 0: y, m = y - 1, 12
    if m == 13: y, m = y + 1, 3
    return f"{y}-{m:02d}"
_mem = sorted({t_ for l_ in ((data.get("sectors") or {}).get("mem") or {}).values() for t_ in l_})
_E = {}
for _t in _mem:
    _p = root / "fund" / f"{_t}.json"
    if not _p.exists(): continue
    try: _f = json.loads(_p.read_text(encoding="utf-8"))
    except Exception: continue
    _m = {}
    for _d, _n in zip(_f.get("q") or [], _f.get("ni") or []):
        if _n is not None: _m[_cq(_d)] = _n
    if _m: _E[_t] = _m
if _E:
    _qs = sorted({q for m in _E.values() for q in m})
    # the range: from the first quarter most members have (the SEC files hold ~20 quarters) to the newest one 85% have already reported
    _cov = lambda q: sum(1 for m in _E.values() if q in m) / len(_E)
    while _qs and _cov(_qs[-1]) < 0.85: _qs.pop()
    while _qs and _cov(_qs[0]) < 0.9: _qs.pop(0)
    _set = [t for t, m in _E.items() if all(q in m for q in _qs)]
    _sum = [sum(_E[t][q] for t in _set) for q in _qs]
    _ttm = [(_qs[i], sum(_sum[i - 3:i + 1])) for i in range(3, len(_qs))]
    write("spxe.json", js({"q": [q for q, _ in _ttm], "e": [round(v / 1e9, 1) for _, v in _ttm], "qs": _qs, "qe": [round(v / 1e9, 1) for v in _sum],
                           "n": len(_set), "of": len(_mem), "src": "SEC EDGAR"}))


# ---------- stock universe ----------
write("stocks.json", js({"asOf": themes.get("asOf"), "stocks": stocks, "ex": exch,
                         "he": {t: n for t, n in he_names.items() if t in universe}}))

# ---------- analysts + screener extras ----------
try: _an = json.loads((root / "analysts.json").read_text(encoding="utf-8"))
except Exception: _an = {}
_rec, _nx = _an.get("rec", {}), _an.get("next", {})
def _capn(c):
    m = re.fullmatch(r"([\d.]+)([TBM])", str(c or "")); return float(m[1]) * {"T": 1e12, "B": 1e9, "M": 1e6}[m[2]] if m else 0
_insb = {}
for _r in (data.get("insiders") or {}).get("rows", []):
    if _r.get("type") == "P": _insb[_r["t"]] = _insb.get(_r["t"], 0) + _r.get("val", 0)
import datetime as _dts
_scr = {}
for _ind, _lst in stocks.items():
    for _s in _lst:
        _t = _s[0]; _x = {}
        try:
            _f = json.loads((root / "fund" / f"{_t}.json").read_text())
            _q, _rv, _ni = _f.get("q") or [], _f.get("rev") or [], _f.get("ni") or []
            if len(_q) >= 4 and (_dts.date.today() - _dts.date.fromisoformat(_q[-1])).days < 200:
                _c = _capn(_s[2]); _r4 = [v for v in _rv[-4:] if v]; _n4 = [v for v in _ni[-4:] if v is not None]
                if len(_r4) == 4 and sum(_r4) > 0 and _c: _x["ps"] = round(_c / sum(_r4), 1)
                if len(_n4) == 4 and sum(_n4) > 0 and _c and _c / sum(_n4) < 1000: _x["pe"] = round(_c / sum(_n4), 1)
                if len(_n4) == 4 and len(_r4) == 4 and sum(_r4) > 0: _x["nm"] = round(sum(_n4) / sum(_r4) * 100, 1)   # net margin, TTM
                _d0 = _dts.date.fromisoformat(_q[-1])
                for _i in range(len(_q) - 2, -1, -1):
                    if 340 <= (_d0 - _dts.date.fromisoformat(_q[_i])).days <= 390 and _rv[_i] and _rv[-1] and _rv[_i] > 0:
                        _g = (_rv[-1] / _rv[_i] - 1) * 100
                        if -95 < _g < 900: _x["g"] = round(_g, 1)
                        break
                # annual growth: last 4 quarters vs the 4 before them (needs 8 contiguous quarters)
                if len(_q) >= 8 and len(_rv) >= 8 and all(_rv[-8:]) and 600 <= (_d0 - _dts.date.fromisoformat(_q[-8])).days <= 700:
                    _p4, _c4 = sum(_rv[-8:-4]), sum(_rv[-4:])
                    if _p4 > 0 and -95 < (_c4 / _p4 - 1) * 100 < 900: _x["ga"] = round((_c4 / _p4 - 1) * 100, 1)
        except Exception: pass
        if _t in _insb: _x["ib"] = int(_insb[_t])
        _e = (earn.get(_t) or {}).get("d") if isinstance(earn.get(_t), dict) else None
        _e = _e or (_nx.get(_t) or {}).get("d")
        if _e and str(_e)[:10] >= _dts.date.today().isoformat(): _x["e"] = str(_e)[:10]
        _rc = (_rec.get(_t) or {}).get("now")
        if _rc and sum(_rc) >= 3: _x["bp"] = round((_rc[0] + _rc[1]) / sum(_rc) * 100)   # % of analysts rating buy
        if _x: _scr[_t] = _x
write("screen.json", js({"asOf": themes.get("asOf"), "x": _scr}))

# ---------- last quarters: EPS vs estimate (Finnhub) + revenue and year-over-year (SEC fund files, report cards) ----------
try: _eh = json.loads((root / "earnhist.json").read_text(encoding="utf-8"))
except Exception: _eh = {}
_ehh = _eh.get("h", {})
_cards = {}
for _r in data.get("reports", []): _cards.setdefault(_r.get("t"), []).append(_r)
def _yoy(a, b):
    if a is None or b is None or b <= 0: return None
    g = (a / b - 1) * 100
    return round(g) if -99 <= g <= 999 else None
def earn_hist(t):
    rows = _ehh.get(t) or []
    if not rows: return None
    D = _dts.date.fromisoformat
    try: f = json.loads((root / "fund" / f"{t}.json").read_text())
    except Exception: f = {}
    fq, frv, fe = f.get("q") or [], f.get("rev") or [], f.get("eps") or []
    def near(day, lst, lo, hi):   # index of the date in lst whose distance from day is within [lo, hi] days, closest to the middle
        best = None
        for i, x in enumerate(lst):
            try: dd = (day - D(x)).days
            except Exception: continue
            if lo <= dd <= hi and (best is None or abs(dd - (lo + hi) / 2) < best[0]): best = (abs(dd - (lo + hi) / 2), i)
        return None if best is None else best[1]
    # Finnhub labels a quarter by the calendar quarter-end on or after the real fiscal quarter-end (Nvidia's quarter that
    # ends in late October is "12-31"), so the SEC quarter is the one that ended 0-85 days before the label (a few days after for 53-week years)
    per = [r[0] for r in rows]; out = []; ok = 0
    cards = sorted(_cards.get(t, []), key=lambda c: str(c.get("date", "")), reverse=True)
    if any(abs(r[3]) > 500 for r in rows[:4]): return None        # per-share figures of another share class (Berkshire A)
    for k, r in enumerate(rows[:4]):
        p, y, q, a, e = r; day = D(p)
        x = {"q": (f"Q{q} {str(y)[-2:]}" if q and y else p[:7]), "a": a}
        if e is not None: x["e"] = e
        j = near(day, per, 335, 395)                      # same quarter a year earlier, adjusted (Finnhub)
        if j is not None:
            x["ay"] = _yoy(a, rows[j][3])
            if x["ay"] is not None: x["pa"] = rows[j][3]          # the same quarter a year earlier (adjusted), for the table
        i = near(day, fq, -8, 85)
        if i is not None: ok += 1
        if x.get("ay") is None and i is not None and i < len(fe):
            j2 = near(D(fq[i]), fq, 335, 395)
            if j2 is not None and j2 < len(fe) and fe[i] is not None and fe[j2] is not None:
                g_ = _yoy(fe[i], fe[j2])
                if g_ is not None and abs(g_) <= 300: x["ay"] = g_; x["g"] = 1; x["ga"] = round(fe[i], 2); x["pa"] = round(fe[j2], 2)   # GAAP year-over-year (skipped when the GAAP base is tiny); both GAAP figures for the table
        if i is not None and i < len(frv) and frv[i]:
            x["r"] = round(frv[i] / 1e9, 3)
            j2 = near(D(fq[i]), fq, 335, 395)
            if j2 is not None and j2 < len(frv):
                x["ry"] = _yoy(frv[i], frv[j2])
                if x["ry"] is not None and frv[j2]: x["pr"] = round(frv[j2] / 1e9, 3)
        elif k == 0 and len(fq) >= 4:                                      # newest quarter not in the SEC file yet: revenue from the report card (same EPS = same quarter)
            for c in cards[:1]:
                if isinstance(c.get("epsAct"), (int, float)) and abs(c["epsAct"] - a) <= max(0.02, abs(a) * 0.02):
                    ok += 1
                    if isinstance(c.get("revAct"), (int, float)): x["r"] = c["revAct"]
                    if isinstance(c.get("revYoy"), (int, float)) and abs(c["revYoy"]) < 1000: x["ry"] = round(c["revYoy"])
        if k == 0 and x.get("ay") is None and len(fq) >= 4:   # newest quarter: EPS year-over-year from our report card, when it has one
            for c in cards[:1]:
                if isinstance(c.get("epsAct"), (int, float)) and abs(c["epsAct"] - a) <= max(0.02, abs(a) * 0.02) and isinstance(c.get("epsYoy"), (int, float)):
                    x["ay"] = round(c["epsYoy"])
        out.append({k2: v for k2, v in x.items() if v is not None})
    # companies that do not file quarterly with the SEC (foreign filers): Finnhub may give EPS in the local currency,
    # so the table is shown only when the quarters are matched to the SEC file
    if not ok: return None
    return out if out else None

# ---------- per-stock details ----------
_rep_by = {}
for _r in reports:
    if _r.get("t"): _rep_by.setdefault(_r["t"], []).append(_r)
_CO_SUFFIX = re.compile(r",? (Inc|Corp|Corporation|Ltd|plc|Holdings?|Group|Company|Co)\.?$", re.I)
def _stock_news(t):
    """Same match as stockNews() on the page: tagged with the ticker, or the company's first name / the ticker in the title."""
    co = (universe.get(t) or ("",))[0] or ""
    nm = _CO_SUFFIX.sub("", co).split(" ")[0].lower() if co else ""
    rx = re.compile(r"\b" + re.escape(t) + r"\b")
    out = []
    for n in news:
        tk = n.get("t") or n.get("tickers") or []
        hay = ((n.get("tag") or "") + " " + (n.get("title") or "")).lower()
        if (isinstance(tk, list) and t in tk) or (len(nm) > 2 and nm in hay) or rx.search(n.get("title") or ""):
            out.append(n)
            if len(out) >= 8: break
    return out
def _roe_of(t):
    """ROE = net income of the last 4 quarters / average equity (assets - liabilities) now and a year earlier, from the SEC file."""
    try: f = json.loads((root / "fund" / f"{t}.json").read_text(encoding="utf-8"))
    except Exception: return None
    q, ni, a, l = f.get("q") or [], f.get("ni") or [], f.get("assets") or [], f.get("liab") or []
    if len(q) < 4 or len(ni) < len(q) or len(a) < len(q) or len(l) < len(q): return None
    last4 = ni[-4:]
    if any(x is None for x in last4): return None
    try:   # the 4 quarters must be consecutive (about a year apart end to end)
        if not 250 <= (_dt.date.fromisoformat(q[-1]) - _dt.date.fromisoformat(q[-4])).days <= 300: return None
    except ValueError: return None
    eq = [a[i] - l[i] for i in (-1, -5 if len(q) >= 5 else -4) if a[i] is not None and l[i] is not None]
    if not eq or min(eq) <= 0: return None   # negative equity: ROE means nothing
    return {"v": round(sum(last4) / (sum(eq) / len(eq)) * 100, 1), "q": q[-1]}
n_s = 0
for t in sorted(set(universe) | set(profiles) | set(facts) | set(earn)):
    if not re.fullmatch(r"[A-Z0-9.\-]{1,10}", t):
        continue
    rec = {"p": profiles.get(t) or {}, "f": dict(facts.get(t) or {}), "e": earn.get(t)}
    rec["f"].pop("siAt", None)
    _roe = _roe_of(t)
    if _roe: rec["f"]["roe"] = _roe
    if t in _rec or t in _nx: rec["an"] = {"rec": _rec.get(t), "next": _nx.get(t), "asOf": _an.get("asOf")}
    _h = earn_hist(t)
    if _h: rec["eh"] = _h
    # the stock page reads its own reports and news from here, so it does not download the full archives
    _rp = _rep_by.get(t)
    if _rp: rec["rp"] = _rp
    _nw = _stock_news(t)
    if _nw: rec["nw"] = _nw
    # "why did it move": every per-stock item tagged with this ticker (date, Israel day, title, body, source, url)
    if earndates.get(t): rec["ed"] = earndates[t]
    _mv = [[n.get("date"), n.get("tday") or "", n.get("title") or "", n.get("body") or "", n.get("src") or "", n.get("url") or ""]
           for n in news if n.get("k") == "stock" and t in (n.get("t") or [])]
    if _mv: rec["mv"] = _mv[:40]
    if rec["p"] or rec["f"] or rec["e"] or _h:
        n_s += write(f"s/{t}.json", js(rec))

# ---------- index.html ----------
t = (root / "template.html").read_text(encoding="utf-8")
old = '  try { db = window.claude && await window.claude.use("db"); } catch(e) {}\n'
new = '''  try {
    for (let i=0; i<40 && !(window.claude && window.claude.use); i++) await new Promise(r=>setTimeout(r,250));
    if (window.claude && window.claude.use) db = await window.claude.use("db");
  } catch(e) {}
'''
page = t.replace(old, new)

# The big stylesheet and the app script go to their own files (assets/app.<hash>.css / .js): the browser keeps them
# between visits, and only the HTML (with the core data) is downloaded again. Minified with esbuild when it is available
# (pinned version, so a local build and a GitHub build give the same files); otherwise they are written as they are.
import hashlib, re as _re, shutil, subprocess
ESB_V = "0.24.0"
def _esbuild():
    for c in (os.environ.get("ESBUILD"), str(root / "node_modules/.bin/esbuild"), "/tmp/esb/node_modules/.bin/esbuild"):
        if c and pathlib.Path(c).exists():
            try:
                if subprocess.run([c, "--version"], capture_output=True, text=True, timeout=20).stdout.strip() == ESB_V: return [c]
            except Exception: pass
    if shutil.which("npx"): return ["npx", "--yes", f"esbuild@{ESB_V}"]
    return None
ESB = _esbuild()
def minify(text, loader):
    if not ESB: return text
    try:
        r = subprocess.run(ESB + [f"--loader={loader}", "--minify", "--charset=utf8", "--log-level=error"], input=text, capture_output=True, text=True, timeout=180)
        if r.returncode == 0 and len(r.stdout) > len(text) // 5: return r.stdout
        print("esbuild failed, unminified:", r.stderr[:300])
    except Exception as e: print("esbuild failed, unminified:", type(e).__name__, e)
    return text
def asset(text, ext):
    h = hashlib.sha1(text.encode("utf-8")).hexdigest()[:10]
    name = f"assets/app.{h}.{ext}"; write(name, text); return name
m_css = _re.search(r"<style>\n(:root\{.*?)</style>\n", page, _re.S)
m_js = _re.search(r"<script>\nconst FALLBACK = __DATA__;\n(.*?)</script>\n</body>", page, _re.S)
if m_css and m_js:
    css_name = asset(minify(m_css.group(1), "css"), "css")
    js_name = asset(minify(m_js.group(1), "js"), "js")
    page = (page[:m_js.start()] + '<script>const FALLBACK = __DATA__;</script>\n<script src="' + js_name + '" onerror="window.__unboot&&__unboot()"></script>\n</body>' + page[m_js.end():])
    page = page[:m_css.start()] + '<link rel="stylesheet" href="' + css_name + '">\n<link rel="preload" as="script" href="' + js_name + '">\n' + page[m_css.end():]   # the script is at the end of a long page: start its download right away
    # keep the files of the last builds (a page opened a little earlier still finds its own), delete older ones
    kp = root / "assets/keep.json"
    try: keep = json.loads(kp.read_text(encoding="utf-8"))
    except Exception: keep = []
    keep = [n for n in keep if n not in (css_name, js_name)][-10:] + [css_name, js_name]
    write("assets/keep.json", json.dumps(keep, indent=0) + "\n")
    for f in (root / "assets").glob("app.*"):
        if f"assets/{f.name}" not in keep: f.unlink()
else:
    print("WARNING: style/script block not found, index.html keeps them inline")
page = page.replace("__DATA__", core_txt.replace("</", "<\\/"))
write("index.html", page)

# ---------- static stock pages (SEO) ----------
SEC_HE = {"Technology": "טכנולוגיה", "Healthcare": "בריאות", "Financial Services": "פיננסים", "Consumer Cyclical": "צריכה מחזורית",
          "Consumer Defensive": "צריכה בסיסית", "Industrials": "תעשייה", "Energy": "אנרגיה", "Basic Materials": "חומרי גלם",
          "Real Estate": "נדל״ן", "Utilities": "תשתיות", "Communication Services": "תקשורת"}
ind_he = {r.get("en"): r.get("n") for r in themes.get("rows") or []}
ind_sec = themes.get("indSector") or {}
E = lambda s: html.escape(str(s if s is not None else ""), quote=True)

def dmy(d):
    m = re.fullmatch(r"(\d{4})-(\d\d)-(\d\d)", str(d or ""))
    return f"{m[3]}.{m[2]}.{m[1]}" if m else str(d or "")

def money(x):
    if not isinstance(x, (int, float)): return "—"
    a = abs(x); s = "-" if x < 0 else ""
    return f"{s}${a:.2f}B" if a >= 1 else f"{s}${a*1000:.1f}M"

def eps(x):
    return "—" if not isinstance(x, (int, float)) else ("-$" if x < 0 else "$") + f"{abs(x):.2f}"

last_rep = {}
for r in sorted(reports, key=lambda r: str(r.get("date", ""))):
    last_rep[r.get("t")] = r

def stock_news(tk, co):
    first = re.sub(r",? (Inc|Corp|Corporation|Ltd|plc|Holdings?|Group|Company|Co)\.?$", "", co or "", flags=re.I).split(" ")[0].lower()
    out = []
    for n in news:
        tt = n.get("t") or []
        hay = ((n.get("tag") or "") + " " + (n.get("title") or "")).lower()
        if (isinstance(tt, list) and tk in tt) or (len(first) > 2 and first in hay) or re.search(r"\b" + re.escape(tk) + r"\b", n.get("title") or ""):
            out.append(n)
        if len(out) >= 5: break
    return out

CSS = """body{margin:0;background:#0b0f17;color:#e8edf6;font-family:Heebo,system-ui,sans-serif;line-height:1.65;font-size:16px}
a{color:#5b8cff}.w{max-width:820px;margin:0 auto;padding:0 16px}header{border-bottom:1px solid #243049;padding:14px 0}
header a{color:#e8edf6;text-decoration:none;font-weight:800;font-size:20px;display:inline-flex;gap:8px;align-items:center}
header img{width:30px;height:30px}h1{font-size:26px;margin:22px 0 4px;line-height:1.3}h1 .tk{color:#8a97ae;font-size:17px;font-weight:600;direction:ltr;unicode-bidi:isolate}
h2{font-size:19px;margin:26px 0 8px}.meta{color:#8a97ae;font-size:14px}.cta{display:inline-block;margin:16px 0 4px;background:#5b8cff;color:#fff;
padding:12px 18px;border-radius:12px;text-decoration:none;font-weight:700}.card{background:#121826;border:1px solid #243049;border-radius:14px;padding:14px;margin:8px 0}
.facts{display:flex;gap:6px 18px;flex-wrap:wrap;color:#8a97ae;font-size:14px}.facts span{white-space:nowrap}.nw b{display:block}.nw small{color:#8a97ae}
.peers{display:flex;gap:8px;flex-wrap:wrap}.peers a{background:#182033;border:1px solid #243049;border-radius:9px;padding:6px 10px;text-decoration:none;color:#e8edf6;font-size:14px}
footer{color:#8a97ae;font-size:13px;border-top:1px solid #243049;margin-top:34px;padding:16px 0 40px}.num{direction:ltr;unicode-bidi:isolate}"""

# the site is for signed-in visitors only: anyone else is sent to the landing page (/join) and returns to this stock after sign-up
STOCK_GATE = """<script>(function(){try{if(/(?:^|; )__client_uat=[1-9]/.test(document.cookie)||localStorage.getItem('clkOn')==='1')return;sessionStorage.setItem('lpNext','#stock/TK');location.replace('/join');}catch(e){}})();</script>
"""
def stock_page(tk):
    co, cap, ind = universe.get(tk, (None, None, None))
    r = last_rep.get(tk)
    if not co and r: co = r.get("co")
    co = co or tk
    heN = (he_names.get(tk) or "").split(" ")[0]
    prof = profiles.get(tk) or {}
    F = facts.get(tk) or {}
    sec = ind_sec.get(ind, "")
    secHe, indHe = SEC_HE.get(sec, (r or {}).get("sector", "")), ind_he.get(ind, "")
    title = f"מניית {heN + ' ' if heN else ''}{co} ({tk}) – תעודת זהות, דוחות וחדשות | וולסטריטר"
    desc = prof.get("desc") or f"{co} ({tk}) בעברית: על החברה, הדוח האחרון, תאריך הדוח הבא, חדשות וגרף מניה."
    desc = re.sub(r"\s+", " ", desc)
    if len(desc) > 158: desc = desc[:155].rsplit(" ", 1)[0] + "…"
    url = f"{SITE}stock/{tk}.html"
    app = f"../#stock/{tk}"
    parts = [f"<h1>{E(heN) + ' – ' if heN else ''}<bdi>{E(co)}</bdi> <small class=tk>{E(tk)}</small></h1>",
             f'<div class="meta">{" · ".join(E(x) for x in [secHe and "סקטור: " + secHe, indHe and "תעשייה: " + indHe, exch.get(tk)] if x)}</div>',
             f'<a class="cta" href="{E(app)}">לגרף, לנתונים ולעמוד המלא באתר ←</a>']
    about = prof.get("about") or prof.get("desc")
    fx = []
    if F.get("hq"): fx.append(f"<span>מטה: <bdi>{E(F['hq'])}</bdi></span>")
    if F.get("emp"): fx.append(f"<span>עובדים: <span class=num>{int(F['emp']):,}</span></span>")
    if F.get("web"):
        host = re.sub(r"^https?://(www\.)?", "", F["web"]).rstrip("/")
        fx.append(f'<a href="{E(F["web"])}" rel="nofollow noopener">{E(host)}</a>')
    if about or fx:
        parts.append("<h2>על החברה</h2>" + "".join(f"<p>{E(p)}</p>" for p in re.split(r"\n+", about or "") if p.strip())
                     + (f'<div class="facts">{"".join(fx)}</div>' if fx else ""))
    e = earn.get(tk)
    if e and e.get("d"):
        parts.append(f"<h2>הדוח הבא</h2><p>{dmy(e['d'])}{' (הערכה)' if e.get('est') else ''}</p>")
    if r:
        rows = [f"<b>{E(r.get('q'))} · פורסם ב-{dmy(r.get('date'))}</b>",
                f"רווח למניה: <span class=num>{eps(r.get('epsAct'))}</span> (צפי <span class=num>{eps(r.get('epsEst'))}</span>)"]
        if isinstance(r.get("revAct"), (int, float)):
            rows.append(f"מכירות: <span class=num>{money(r.get('revAct'))}</span> (צפי <span class=num>{money(r.get('revEst'))}</span>)")
        if r.get("guideText"): rows.append("תחזית: " + E(r["guideText"]))
        if r.get("note"): rows.append(E(r["note"]))
        parts.append('<h2>הדוח האחרון</h2><div class="card">' + "<br>".join(rows) + "</div>")
    nn = stock_news(tk, co)
    if nn:
        parts.append("<h2>חדשות אחרונות</h2>" + "".join(
            f'<div class="card nw"><small>{dmy(n.get("date"))}</small><b>{E(n.get("title"))}</b>{E(n.get("body"))}</div>' for n in nn))
    peers = [s for s in stocks.get(ind, []) if s[0] != tk][:10]
    if peers:
        parts.append(f"<h2>חברות נוספות בתעשייה{(': ' + E(indHe)) if indHe else ''}</h2><div class=\"peers\">" +
                     "".join(f'<a href="{E(p[0])}.html">{E(p[0])} · {E(p[1])}</a>' for p in peers) + "</div>")
    ld = {"@context": "https://schema.org", "@type": "Corporation", "name": co, "tickerSymbol": tk}
    if F.get("web"): ld["url"] = F["web"]
    return f"""<!DOCTYPE html>
<html lang="he" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
{STOCK_GATE.replace("TK", tk)}<title>{E(title)}</title><meta name="description" content="{E(desc)}"><link rel="canonical" href="{url}">
<meta property="og:title" content="{E(title)}"><meta property="og:description" content="{E(desc)}"><meta property="og:url" content="{url}">
<meta property="og:site_name" content="וולסטריטר"><meta property="og:locale" content="he_IL"><meta name="theme-color" content="#0b0f17">
<link rel="icon" type="image/svg+xml" href="../logo.svg"><link rel="manifest" href="../manifest.webmanifest">
<script type="application/ld+json">{js(ld).replace("</", "<\\/")}</script><link rel="stylesheet" href="../stock.css"></head>
<body><header><div class="w"><a href="../"><img src="../logo.svg" alt="">וולסטריטר</a></div></header>
<main class="w">{"".join(parts)}</main>
<footer class="w">וולסטריטר – השוק האמריקאי, בגובה העיניים. המידע באתר הוא מידע כללי בלבד ואינו ייעוץ השקעות או המלצה לקנות או למכור ניירות ערך.
<a href="../#terms">תנאי שימוש</a> · <a href="../">לעמוד הראשי</a></footer></body></html>
"""

write("stock.css", CSS + "\n")
pages = sorted(t for t in set(universe) | {r.get("t") for r in reports if r.get("t")} if re.fullmatch(r"[A-Z0-9.\-]{1,10}", t or ""))
n_p = sum(write(f"stock/{tk}.html", stock_page(tk)) for tk in pages)

sm = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">', f"<url><loc>{SITE}</loc></url>", f"<url><loc>{SITE}join</loc></url>"]
sm += [f"<url><loc>{SITE}stock/{tk}.html</loc></url>" for tk in pages]
write("sitemap.xml", "\n".join(sm + ["</urlset>", ""]))

print(f"built: index.html {len(page)//1024}KB, core.json {len(core_txt)//1024}KB, {len(pages)} stock pages ({n_p} changed), {n_s} stock files changed")
