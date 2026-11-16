"""Nightly: industry (theme) performance + per-industry stock lists, from Yahoo Finance.
Universe: US equities with market cap > $1B (Yahoo screener). Industry names match Finviz's.
Group performance = equal-weight average of members (Finviz-style windows)."""
import json, pathlib, time
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
    r = yf.screen(q, offset=off, size=250, sortField="intradaymarketcap", sortAsc=False)
    qs = r.get("quotes", [])
    for x in qs:
        if x.get("quoteType") == "EQUITY" and x.get("marketCap") and x.get("exchange") in EXCH:
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

# 3) prices
frames = []
for i in range(0, len(known), 400):
    px = yf.download(known[i:i+400], period="14mo", interval="1d", auto_adjust=True,
                     group_by="column", threads=True, progress=False)["Close"]
    frames.append(px)
close = pd.concat(frames, axis=1)
close = close.loc[:, ~close.columns.duplicated()].dropna(how="all")
last = close.index[-1]
def ret(n):
    v = (close.iloc[-1] / close.iloc[-1 - n] - 1) * 100
    v[close.iloc[-1 - n].isna()] = float("nan"); return v
py = close[close.index.year < last.year]
R = {"d": ret(1), "w": ret(5), "m": ret(21), "q": ret(63), "h": ret(126), "y": ret(252),
     "ytd": (close.iloc[-1] / py.iloc[-1] - 1) * 100}

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
        if len(v): rows[ind][k] = round(float(v.mean()), 2)
    lst = []
    for s in mem:
        x = uni[s]; rr = {k: (None if pd.isna(R[k].get(s)) else round(float(R[k][s]), 2)) for k in R}
        lst.append([s, x.get("shortName") or x.get("longName") or s, cap(x["marketCap"]), rr])
    stocks[ind] = lst
T["stocks"] = stocks
EXN = {"NMS": "NASDAQ", "NGM": "NASDAQ", "NCM": "NASDAQ", "NYQ": "NYSE", "ASE": "AMEX", "PCX": "AMEX", "BTS": "CBOE"}
T["ex"] = {s: EXN.get(uni[s].get("exchange"), "") for s in close.columns}
T["indSector"] = {}
for s in close.columns:
    ind, sec = cache[s][0], cache[s][1]
    if ind and sec: T["indSector"].setdefault(ind, sec)
T["stocksSrc"] = "Yahoo Finance"
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

(root / "data.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
