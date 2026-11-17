"""Nightly update: S&P 500 breadth + sector performance (equal-weight, Finviz-style windows).
Data: Yahoo Finance via yfinance. Constituents: datasets/s-and-p-500-companies on GitHub."""
import json, pathlib, io, urllib.request
import pandas as pd, yfinance as yf

root = pathlib.Path(__file__).resolve().parent.parent
data_path = root / "data.json"
data = json.loads(data_path.read_text(encoding="utf-8"))

CSV = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"
sp = pd.read_csv(io.StringIO(urllib.request.urlopen(CSV, timeout=60).read().decode()))
sp["yf"] = sp["Symbol"].str.replace(".", "-", regex=False)
tickers = sp["yf"].tolist()

px = yf.download(tickers, period="14mo", interval="1d", auto_adjust=True,
                 group_by="column", threads=True, progress=False)
close, high, low = px["Close"], px["High"], px["Low"]
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
ma50 = close.rolling(50).mean().iloc[-1]; ma200 = close.rolling(200).mean().iloc[-1]
c = close.iloc[-1]
hi52 = high.iloc[-252:-1].max(); lo52 = low.iloc[-252:-1].min()
row = {
    "d": f"{last.day}.{last.month}",
    "up": int((r1 > 0).sum()), "dn": int((r1 < 0).sum()),
    # % of S&P 500 members whose last close is above their simple MA, counted only over members
    # that have enough history for that MA — the same definition as S5FI (50-day) / S5TH (200-day)
    "ma50": round(float((c > ma50)[ma50.notna() & c.notna()].mean() * 100), 1),
    "ma200": round(float((c > ma200)[ma200.notna() & c.notna()].mean() * 100), 1),
    "hi": int((high.iloc[-1] >= hi52).sum()), "lo": int((low.iloc[-1] <= lo52).sum()),
    "up10": int((r21 >= 10).sum()), "dn10": int((r21 <= -10).sum()),
}
b = data.get("breadth", {"rows": []})
import re as _re, datetime as _dt
_m = _re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", b.get("asOf", ""))
_prev = _dt.date(int(_m.group(3)), int(_m.group(2)), int(_m.group(1))) if _m else None
if _prev and last.date() < _prev:
    print("breadth: Yahoo returned older data than we already have — keeping existing", last.date(), _prev)
else:
    rows = [r for r in b.get("rows", []) if r.get("d") != row["d"]]
    b["rows"] = [row] + rows[:9]
    b["asOf"] = f"סגירת {last.day}.{last.month}.{last.year}"
    data["breadth"] = b

# ---- sectors: equal-weight average of S&P 500 members per GICS sector ----
GICS = {"Information Technology": "XLK", "Communication Services": "XLC", "Consumer Discretionary": "XLY",
        "Consumer Staples": "XLP", "Energy": "XLE", "Financials": "XLF", "Health Care": "XLV",
        "Industrials": "XLI", "Real Estate": "XLRE", "Materials": "XLB", "Utilities": "XLU"}
sec_of = dict(zip(sp["yf"], sp["GICS Sector"]))
for srow in data["sectors"]["rows"]:
    g = [k for k, v in GICS.items() if v == srow["t"]]
    if not g: continue
    members = [t for t in good if sec_of.get(t) == g[0]]
    for k, s in R.items():
        v = s.reindex(members).dropna()
        if len(v): srow[k] = round(float(v.mean()), 2)
import datetime, zoneinfo
now = datetime.datetime.now(zoneinfo.ZoneInfo("Asia/Jerusalem"))
live = now.date() == last.date() and now.hour < 23
stamp = (f"{last.day}.{last.month}.{last.year} בשעה {now:%H:%M} (שעון ישראל, בעיכוב של כ-15 דקות)" if live
         else f"סגירת {last.day}.{last.month}.{last.year}")
data["sectors"]["asOf"] = stamp + " · ממוצע מניות ה-S&P 500 בכל סקטור"

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
    data["movers"] = {"asOf": stamp, "rows": mv[:40]}
    print("movers", len(mv))
except Exception as e:
    print("movers failed", e)

data_path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
print("breadth", row)
