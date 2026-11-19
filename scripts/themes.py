"""Nightly: industry (theme) performance + per-industry stock lists, from Yahoo Finance.
Universe: US equities with market cap > $1B and avg daily volume >= 500k (Yahoo screener). Industry names match Finviz's.
Group performance = equal-weight average of members (Finviz-style windows)."""
import urllib.request, json, pathlib, time
import pandas as pd, yfinance as yf
from yfinance import EquityQuery

root = pathlib.Path(__file__).resolve().parent.parent
data = json.loads((root / "data.json").read_text(encoding="utf-8"))
cache_p = root / "industries.json"
cache = json.loads(cache_p.read_text(encoding="utf-8")) if cache_p.exists() else {}

EXCH = {"NMS", "NGM", "NCM", "NYQ", "ASE", "PCX", "BTS"}  # Nasdaq / NYSE / NYSE American / Arca / Cboe
# 1) universe
q = EquityQuery("and", [EquityQuery("eq", ["region", "us"]),
                        EquityQuery("gt", ["intradaymarketcap", 1_000_000_000])])
uni, off = {}, 0
while True:
    for _try in range(4):
        try:
            r = yf.screen(q, offset=off, size=250, sortField="intradaymarketcap", sortAsc=False); break
        except Exception as e:
            print("screen retry", _try, type(e).__name__, flush=True); time.sleep(10 * (_try + 1))
    else:
        raise SystemExit("Yahoo screener unavailable — keeping previous themes data")
    qs = r.get("quotes", [])
    for x in qs:
        # site rules: cap > $1B, major exchange, average daily volume (3 months) >= 500k shares
        if x.get("quoteType") == "EQUITY" and x.get("marketCap") and x.get("exchange") in EXCH \
           and (x.get("averageDailyVolume3Month") or 0) >= 500_000:
            uni[x["symbol"]] = x
    off += 250
    total = r.get("total", 0)
    if not qs or off >= total: break
    time.sleep(0.5)
print("universe", len(uni), "total", total, "sample keys", sorted(next(iter(uni.values())).keys())[:60])

# 2) industry per symbol (cached; screener field if present, else .info, limited per run)
fetched = 0
for s, x in uni.items():
    if s in cache: continue
    if x.get("industry"):
        cache[s] = [x["industry"], x.get("sector", "")]; continue
    if fetched >= 1500: continue
    try:
        info = yf.Ticker(s).info
        cache[s] = [info.get("industry") or "", info.get("sector") or ""]
    except Exception as e:
        print("info fail", s, e)
    fetched += 1
    time.sleep(0.15)
cache_p.write_text(json.dumps(cache, ensure_ascii=False, indent=0), encoding="utf-8")
known = [s for s in uni if cache.get(s, [""])[0]]
print("info fetched", fetched, "with industry", len(known), "/", len(uni))
cover = len([s for s in uni if s in cache]) / max(len(uni), 1)
print("coverage", round(cover, 3))
if cover < 0.95:
    print("industry cache still filling - keeping previous themes/ytd data"); raise SystemExit(0)

# 3) prices: our Massive-built history (verified closes) + Yahoo only for the newest sessions / missing tickers
import hist as H
HIST = H.load()
if len(HIST) and H.KEY:
    HIST, _rep = H.update(HIST, set(HIST.columns) | set(known))
    print("history update", _rep, flush=True)
    if _rep["added"] or _rep["splits"]:
        try: H.save(HIST)
        except Exception as e: print("history save failed", e, flush=True)
in_hist = [s for s in known if len(HIST) and s in HIST.columns and HIST[s].iloc[-260:].notna().sum() >= 30]
frames = []
need_full = [s for s in known if s not in in_hist]
for i in range(0, len(need_full), 400):
    px = yf.download(need_full[i:i+400], period="14mo", interval="1d", auto_adjust=False,
                     group_by="column", threads=True, progress=False)["Close"]
    if isinstance(px, pd.Series): px = px.to_frame(need_full[i])
    frames.append(px)
if in_hist:
    base = HIST[in_hist].copy()
    recent = []
    for i in range(0, len(in_hist), 400):
        try:
            px = yf.download(in_hist[i:i+400], period="10d", interval="1d", auto_adjust=False, group_by="column", threads=True, progress=False)["Close"]
            if isinstance(px, pd.Series): px = px.to_frame(in_hist[i])
            recent.append(px)
        except Exception as e: print("recent chunk failed", type(e).__name__, flush=True)
    if recent:
        rc = pd.concat(recent, axis=1); rc.index = rc.index.tz_localize(None) if rc.index.tz is not None else rc.index
        # different price scale between Massive and Yahoo (split / ADR ratio): align our history to Yahoo on the overlap
        ov = rc.index.intersection(base.index)
        if len(ov):
            ratio = (rc.loc[ov].median() / base.loc[ov].median()).reindex(base.columns)
            bad = ratio[(ratio - 1).abs() > 0.3].dropna()
            for t, k in bad.items(): base[t] = base[t] * k
            if len(bad): print("rescaled history to Yahoo scale", {t: round(float(k), 3) for t, k in bad.items()}, flush=True)
        newer = rc[rc.index > base.index[-1]]
        if len(newer): base = pd.concat([base, newer.reindex(columns=base.columns)])
        print("history last", base.index[-2 if len(newer) else -1].date(), "+ Yahoo sessions", [str(x.date()) for x in newer.index], flush=True)
    frames.append(base)
close = pd.concat(frames, axis=1) if frames else pd.DataFrame()
close = close.loc[:, ~close.columns.duplicated()]
close.index = pd.to_datetime(close.index); close = close.sort_index()
close = close[~close.index.duplicated(keep="last")]
CHECK = {"src": "Massive (מאגר מחירים מבוקר) + Yahoo לימים האחרונים" if in_hist else "Yahoo Finance", "hist": len(in_hist),
         "histTo": str(HIST.index[-1].date()) if len(HIST) else None, "checked": 0, "fixed": 0}
# retry tickers whose download failed (Yahoo throttles big batches)
for _try in range(2):
    miss = [s for s in known if s not in close.columns or close[s].dropna().shape[0] < 30]
    if not miss: break
    print("price retry", _try, len(miss), flush=True); time.sleep(20)
    for i in range(0, len(miss), 150):
        try:
            px = yf.download(miss[i:i+150], period="14mo", interval="1d", auto_adjust=False,
                             group_by="column", threads=False, progress=False)["Close"]
            if isinstance(px, pd.Series): px = px.to_frame(miss[i])
            for col in px.columns:
                if px[col].notna().sum() >= 30: close[col] = px[col]
        except Exception as e:
            print("retry chunk failed", type(e).__name__, flush=True)
close = close.dropna(how="all")
# Yahoo sometimes has the newest day for only a few tickers: drop trailing rows most stocks lack
while len(close) and close.iloc[-1].notna().mean() < 0.9:
    print("dropping sparse last row", close.index[-1].date(), round(close.iloc[-1].notna().mean(), 3)); close = close.iloc[:-1]
okp = sum(1 for s in known if s in close.columns and close[s].dropna().shape[0] >= 30) / max(len(known), 1)
print("price coverage", round(okp, 3))
if okp < 0.9:
    print("too many price downloads failed - keeping previous themes/ytd data"); raise SystemExit(0)
import re as _re, datetime as _dt0
_m = _re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", data.get("themes", {}).get("asOf", ""))
if _m and close.index[-1].date() < _dt0.date(int(_m.group(3)), int(_m.group(2)), int(_m.group(1))):
    print("Yahoo returned older prices than current themes - keeping previous returns, applying universe filter only")
    T0 = data["themes"]; keep = set(uni)
    for ind in list(T0["stocks"]):
        T0["stocks"][ind] = [s for s in T0["stocks"][ind] if s[0] in keep]
        if not T0["stocks"][ind]: del T0["stocks"][ind]
    for r in T0["rows"]:
        lst = T0["stocks"].get(r["en"], [])
        for k in ("d", "w", "m", "q", "h", "ytd", "y"):
            v = [s[3][k] for s in lst if isinstance(s[3], dict) and s[3].get(k) is not None]
            if v and len(v) >= 0.6 * len(lst): r[k] = round(sum(v) / len(v), 2)
    T0["rows"] = [r for r in T0["rows"] if r["en"] in T0["stocks"]]
    (root / "data.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    raise SystemExit(0)
last = close.index[-1]
# cross-check against Yahoo's live quotes of the same session (price + day change vs Yahoo's own previous close):
# a stock whose last close is on another price scale (split / ADR ratio the feeds disagree on) is rescaled
try:
    _lj = json.loads(urllib.request.urlopen("https://raw.githubusercontent.com/sagirozio/wallstreet-he/live/live.json", timeout=30).read().decode())
except Exception as _e: _lj = {}; print("live.json cross-check skipped", _e)
if _lj.get("date") == last.strftime("%Y-%m-%d"):
    _fix = {}
    for _t, _v in (_lj.get("q") or {}).items():
        if _t not in close.columns or not _v or _v[1] is None: continue
        _c = close[_t].dropna()
        if len(_c) < 2 or _c.index[-1] != last: continue
        _prev_y = _v[0] / (1 + _v[1] / 100)                 # Yahoo's previous close
        _k_last, _k_prev = _v[0] / _c.iloc[-1], _prev_y / _c.iloc[-2]
        if abs(_k_last - 1) > 0.3 or abs(_k_prev - 1) > 0.3:   # our series is on another scale
            close.loc[close.index < last, _t] *= _k_prev; close.loc[last, _t] = _v[0]; _fix[_t] = (round(_k_prev, 3), round(_k_last, 3))
    if _fix: print("rescaled to Yahoo live quotes", _fix, flush=True)
HI52 = (close.iloc[-1] / close.iloc[-252:].max() - 1) * 100
def ret(n):
    v = (close.iloc[-1] / close.iloc[-1 - n] - 1) * 100
    v[close.iloc[-1 - n].isna()] = float("nan"); return v
py = close[close.index.year < last.year]
R = {"d": ret(1), "w": ret(5), "m": ret(21), "q": ret(63), "h": ret(126), "y": ret(252),
     "ytd": (close.iloc[-1] / py.iloc[-1] - 1) * 100}

# 3b) ADR% (average daily range): mean of (high / low - 1) over the last 20 sessions, from Yahoo daily bars
ADR = {}
try:
    _all = list(close.columns)
    for i in range(0, len(_all), 400):
        try:
            hl = yf.download(_all[i:i+400], period="1mo", interval="1d", auto_adjust=False, group_by="column", threads=True, progress=False)
            hi_, lo_ = hl["High"], hl["Low"]
            if isinstance(hi_, pd.Series): hi_, lo_ = hi_.to_frame(_all[i]), lo_.to_frame(_all[i])
            rng = ((hi_ / lo_ - 1) * 100).tail(20)
            for t in rng.columns:
                v = rng[t].dropna()
                if len(v) >= 10 and v.median() < 60: ADR[t] = round(float(v.mean()), 1)
        except Exception as e: print("adr chunk failed", type(e).__name__, flush=True)
    print("adr", len(ADR), flush=True)
except Exception as e: print("adr failed", e, flush=True)

# 4) aggregate per industry
def cap(v): return f"{v/1e12:.2f}T" if v >= 1e12 else f"{v/1e9:.2f}B"
by = {}
for s in close.columns:
    ind = cache[s][0]
    by.setdefault(ind, []).append(s)
T = data["themes"]; rows = {r["en"]: r for r in T["rows"]}
stocks = {}
for ind, mem in by.items():
    if ind not in rows or len(mem) < 1: continue
    for k, s in R.items():
        v = s.reindex(mem).dropna()
        # only update when most members have data (otherwise one stock would stand in for the whole industry)
        if len(v) and len(v) >= max(1, 0.6 * len(mem)): rows[ind][k] = round(float(v.mean()), 2)
    lst = []
    for s in mem:
        x = uni[s]; rr = {k: (None if pd.isna(R[k].get(s)) else round(float(R[k][s]), 2)) for k in R}
        _h = HI52.get(s)
        if _h is not None and not pd.isna(_h): rr["hi"] = round(float(_h), 1)   # % below the 52-week closing high (0 = at the high)
        if s in ADR: rr["adr"] = ADR[s]                                        # average daily range %, 20 sessions
        lst.append([s, x.get("shortName") or x.get("longName") or s, cap(x["marketCap"]), rr])
    if sum(1 for e in lst if e[3]["m"] is not None) >= 0.6 * len(lst): stocks[ind] = lst
    elif ind in T.get("stocks", {}): stocks[ind] = [e for e in T["stocks"][ind] if e[0] in uni]
T["stocks"] = stocks
T["rows"] = [r for r in T["rows"] if r["en"] in stocks]   # industries with no qualifying stocks drop out
EXN = {"NMS": "NASDAQ", "NGM": "NASDAQ", "NCM": "NASDAQ", "NYQ": "NYSE", "ASE": "AMEX", "PCX": "AMEX", "BTS": "CBOE"}
T["ex"] = {s: EXN.get(uni[s].get("exchange"), "") for s in close.columns}
# next / latest earnings date per stock (Yahoo screener fields; epoch seconds)
import datetime as _dt
def _d(v):
    try: return _dt.datetime.utcfromtimestamp(int(v)).strftime("%Y-%m-%d")
    except Exception: return None
ed = {}
for s, x in uni.items():
    nxt = _d(x.get("earningsTimestampStart") or x.get("earningsTimestamp"))
    if nxt: ed[s] = {"d": nxt, "est": bool(x.get("isEarningsDateEstimate"))}
data["earnDates"] = ed
print("earnings dates", len(ed))
T["indSector"] = {}
for s in close.columns:
    ind, sec = cache[s][0], cache[s][1]
    if ind and sec: T["indSector"].setdefault(ind, sec)
T["stocksSrc"] = CHECK["src"]
T["check"] = {**CHECK, "date": f"{last.day}.{last.month}.{last.year}"}
T["asOf"] = f"סגירת {last.day}.{last.month}.{last.year}"
missing = [i for i in by if i not in rows]
print("industries matched", len(stocks), "unmatched", missing[:30])

# 5) YTD doublers: >=100% YTD, cap>1B, avg volume (3m) > 800k
dbl = []
for s in close.columns:
    v = R["ytd"].get(s); x = uni[s]
    if close[s].iloc[-260:].notna().sum() < 230: continue   # skip recent IPOs / thin history
    if pd.notna(v) and v >= 100 and (x.get("averageDailyVolume3Month") or 0) >= 800_000:
        dbl.append({"t": s, "n": x.get("shortName") or s, "p": round(float(v), 1),
                    "cap": round(x["marketCap"] / 1e9, 2), "il": x.get("region") == "IL",
                    "vol": round(x.get("averageDailyVolume3Month", 0) / 1e6, 2)})
if dbl:
    dbl.sort(key=lambda r: -r["p"])
    data["ytd"] = {"asOf": f"{last.day}.{last.month}.{last.year}", "rows": dbl, "minVol": 0.8}
print("ytd doublers", len(dbl))

# 6) recent gainers: biggest rises over the last month (21 trading days), cap>1B, avg volume (3m) > 800k
gn = []
for s in close.columns:
    v = R["m"].get(s); x = uni[s]
    if close[s].iloc[-40:].notna().sum() < 30: continue
    if pd.notna(v) and v > 0 and (x.get("averageDailyVolume3Month") or 0) >= 800_000:
        gn.append({"t": s, "n": x.get("shortName") or s, "p": round(float(v), 1),
                   "cap": round(x["marketCap"] / 1e9, 2), "il": x.get("region") == "IL"})
gn.sort(key=lambda r: -r["p"])
if len(gn) >= 10:
    data["gainers"] = {"asOf": f"{last.day}.{last.month}.{last.year}", "period": "חודש", "rows": gn[:15],
                       "large": [r for r in gn if r["cap"] >= 10][:10]}
print("gainers", len(gn))

(root / "data.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
