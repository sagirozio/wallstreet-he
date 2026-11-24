"""Nightly update: S&P 500 breadth + sector performance (equal-weight, Finviz-style windows).
Data: Yahoo Finance via yfinance. Constituents: datasets/s-and-p-500-companies on GitHub."""
import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parent))
import json, pathlib, io, urllib.request
import pandas as pd, yfinance as yf

root = pathlib.Path(__file__).resolve().parent.parent
data_path = root / "data.json"
data = json.loads(data_path.read_text(encoding="utf-8"))

CSV = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"
sp = pd.read_csv(io.StringIO(urllib.request.urlopen(CSV, timeout=60).read().decode()))
sp["yf"] = sp["Symbol"].str.replace(".", "-", regex=False)
tickers = sp["yf"].tolist()

px = yf.download(tickers, period="14mo", interval="1d", auto_adjust=False,
                 group_by="column", threads=True, progress=False)
# dividend-adjusted series (same as auto_adjust=True) + raw highs/lows for the intraday 52-week reference
_f = px["Adj Close"] / px["Close"]
close, high, low = px["Adj Close"], px["High"] * _f, px["Low"] * _f
raw_high, raw_low = px["High"], px["Low"]
close = close.dropna(how="all")
good = [c for c in close.columns if close[c].notna().sum() > 200]
close, high, low = close[good], high[good], low[good]
last = close.index[-1]
print("last date", last.date(), "tickers", len(good))

def ret(n):
    if len(close) <= n: return pd.Series(dtype=float)
    return (close.iloc[-1] / close.iloc[-1 - n] - 1) * 100

prev_year = close[close.index.year < last.year]
ytd = (close.iloc[-1] / prev_year.iloc[-1] - 1) * 100 if len(prev_year) else pd.Series(dtype=float)
R = {"d": ret(1), "w": ret(5), "m": ret(21), "q": ret(63), "h": ret(126), "y": ret(252), "ytd": ytd}

# ---- breadth (S&P 500) ----
r1, r21 = R["d"], R["m"]
# % above the 50 / 200-day average from closes adjusted for splits only, not for dividends (as $S5FI / $S5TH are computed):
# dividend-adjusted closes lower the older prices, so the 200-day average reads too low and ~3 points too many stocks look above it
_rc = px["Close"].reindex(close.index)[close.columns]
ma50 = _rc.rolling(50).mean().iloc[-1]; ma200 = _rc.rolling(200).mean().iloc[-1]
c = _rc.iloc[-1]
hi52 = high.iloc[-252:-1].max(); lo52 = low.iloc[-252:-1].min()
row = {
    "d": f"{last.day}.{last.month}",
    "up": int((r1 > 0).sum()), "dn": int((r1 < 0).sum()),
    # % of S&P 500 members whose last close is above their simple MA, counted only over members
    # that have enough history for that MA — the same definition as S5FI (50-day) / S5TH (200-day)
    # standard ($S5FI / $S5TH, StockCharts $SPXA50R): stocks above their simple average / all index stocks with a price
    "ma50": round(float((c > ma50).sum() / max(1, c.notna().sum()) * 100), 1),
    "ma200": round(float((c > ma200).sum() / max(1, c.notna().sum()) * 100), 1),
    "hi": int((high.iloc[-1] >= hi52).sum()), "lo": int((low.iloc[-1] <= lo52).sum()),
    "up10": int((r21 >= 10).sum()), "dn10": int((r21 <= -10).sum()),
}
def _lst(mask, r, rev=False):
    v = r[mask.reindex(r.index).fillna(False).astype(bool)].dropna().sort_values(ascending=rev)
    return [[t, round(float(x), 1)] for t, x in v.items()]
# the stocks behind the counts (for the day-by-day tracking under the breadth table)
row["L"] = {"hi": _lst(high.iloc[-1] >= hi52, r1), "lo": _lst(low.iloc[-1] <= lo52, r1, True),
            "u": _lst(r21 >= 10, r21), "n": _lst(r21 <= -10, r21, True)}
# 52-week high/low reference (last 251 sessions incl. today, from intraday highs/lows) for tomorrow's intraday breadth
data["ts"] = int(__import__("time").time())   # newer than intra.json -> the site uses core.json
data["hl52"] = {"d": last.strftime("%Y-%m-%d"),
                "hi": {t: round(float(v), 4) for t, v in raw_high.reindex(close.index)[good].iloc[-251:].max().dropna().items()},
                "lo": {t: round(float(v), 4) for t, v in raw_low.reindex(close.index)[good].iloc[-251:].min().dropna().items()}}
b = data.get("breadth", {"rows": []})
import re as _re, datetime as _dt
_m = _re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", b.get("asOf", ""))
_prev = _dt.date(int(_m.group(3)), int(_m.group(2)), int(_m.group(1))) if _m else None
STALE = bool(_prev and last.date() < _prev)
if STALE:
    print("breadth: Yahoo returned older data than we already have — keeping existing", last.date(), _prev)
else:
    rows = [r for r in b.get("rows", []) if r.get("d") != row["d"]]
    b["rows"] = [row] + rows[:19]
    b["asOf"] = f"סגירת {last.day}.{last.month}.{last.year}"
    data["breadth"] = b

# ---- sectors: equal-weight average of S&P 500 members per GICS sector ----
GICS = {"Information Technology": "XLK", "Communication Services": "XLC", "Consumer Discretionary": "XLY",
        "Consumer Staples": "XLP", "Energy": "XLE", "Financials": "XLF", "Health Care": "XLV",
        "Industrials": "XLI", "Real Estate": "XLRE", "Materials": "XLB", "Utilities": "XLU"}
# members of each sector (for the "leaders" list under a sector row)
_mem = {}
for _t, _g in zip(sp["yf"], sp["GICS Sector"]):
    if GICS.get(_g): _mem.setdefault(GICS[_g], []).append(_t)
data.setdefault("sectors", {})["mem"] = _mem
sec_of = dict(zip(sp["yf"], sp["GICS Sector"]))
for srow in ([] if STALE else data["sectors"]["rows"]):
    g = [k for k, v in GICS.items() if v == srow["t"]]
    if not g: continue
    members = [t for t in good if sec_of.get(t) == g[0]]
    for k, s in R.items():
        v = s.reindex(members).dropna()
        if len(v): srow[k] = round(float(v.mean()), 2)
import datetime, zoneinfo
now = datetime.datetime.now(zoneinfo.ZoneInfo("Asia/Jerusalem"))
live = now.date() == last.date() and now.hour < 23
stamp = (f"{last.day}.{last.month}.{last.year} בשעה {now:%H:%M} (שעון ישראל)" if live
         else f"סגירת {last.day}.{last.month}.{last.year}")
# returns as Google Finance / TradingView show them: the sector ETF's own price change (the member averages above stay as a fallback)
_etf_ok = False
if not STALE:
    import sector_etf
    _etf_ok = sector_etf.apply(data)
if _etf_ok and not live and data["sectors"].get("pyDates"):   # the ETF closes may lag (Yahoo) -> show their own date
    _y, _m, _d = map(int, data["sectors"]["pyDates"][-1].split("-")); stamp = f"סגירת {_d}.{_m}.{_y}"
if not STALE: data["sectors"]["asOf"] = stamp + (" · שינוי המחיר של קרן הסל של כל סקטור" if _etf_ok else " · ממוצע מניות ה-S&P 500 בכל סקטור")

# ---- today's big movers: up 10%+ (cap > $1B, avg volume > 800k, major US exchanges) ----
try:
    r = yf.screen("day_gainers", count=250)
    EX = {"NMS", "NGM", "NCM", "NYQ", "ASE", "PCX", "BTS"}
    mv = []
    for q in r.get("quotes", []):
        p = q.get("regularMarketChangePercent") or 0
        if p >= 10 and (q.get("marketCap") or 0) >= 1e9 and (q.get("averageDailyVolume3Month") or 0) >= 800_000 \
           and q.get("exchange") in EX and q.get("quoteType") == "EQUITY":
            mv.append({"t": q["symbol"], "n": q.get("shortName") or q["symbol"], "p": round(float(p), 1)})
    mv.sort(key=lambda x: -x["p"])
    dn = []
    try:
        r2 = yf.screen("day_losers", count=250)
        for q in r2.get("quotes", []):
            p = q.get("regularMarketChangePercent") or 0
            if p <= -10 and (q.get("marketCap") or 0) >= 1e9 and (q.get("averageDailyVolume3Month") or 0) >= 800_000 \
               and q.get("exchange") in EX and q.get("quoteType") == "EQUITY":
                dn.append({"t": q["symbol"], "n": q.get("shortName") or q["symbol"], "p": round(float(p), 1)})
        dn.sort(key=lambda x: x["p"])
    except Exception as e:
        print("losers failed", e)
    # date the movers by the screener's own quote time (the price history used for `stamp` can lag a day)
    mv_stamp = stamp
    try:
        import datetime as _dt
        ts = max(int(q.get("regularMarketTime") or 0) for q in r.get("quotes", []))
        if ts:
            qd = _dt.datetime.fromtimestamp(ts, _dt.timezone(_dt.timedelta(hours=-5))).date()
            if not live: mv_stamp = f"סגירת {qd.day}.{qd.month}.{qd.year}"
    except Exception as e:
        print("movers time", e)
    data["movers"] = {"asOf": mv_stamp, "rows": mv[:40], "down": dn[:20]}
    print("movers", len(mv))
except Exception as e:
    print("movers failed", e)

data_path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
print("breadth", row)
