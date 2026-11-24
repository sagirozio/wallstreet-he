"""Intraday (every 10 min in the session), light: sectors + breadth from our close history + current prices.
Current prices: live.json (Yahoo screener, refreshed every 5 min by live.yml); missing tickers -> one small Yahoo download.
52-week highs/lows: today's intraday high/low (live.json) vs the 52-week range saved nightly (data.json hl52); close-based fallback.
Falls back to update.py when there is no history yet. Movers: same screener logic as update.py."""
import json, pathlib, io, sys, subprocess, urllib.request, datetime as dt
import pandas as pd, yfinance as yf
from zoneinfo import ZoneInfo
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import hist as H
root = pathlib.Path(__file__).resolve().parent.parent
HIST = H.load()
if HIST.empty or len(HIST) < 260:
    print("no usable history -> update.py"); raise SystemExit(subprocess.call([sys.executable, str(root / "scripts" / "update.py")]))
p = root / "data.json"; data = json.loads(p.read_text(encoding="utf-8"))
CSV = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"
sp = pd.read_csv(io.StringIO(urllib.request.urlopen(CSV, timeout=60).read().decode()))
sp["yf"] = sp["Symbol"].str.replace(".", "-", regex=False)
mem = [t for t in sp["yf"] if t in HIST.columns and HIST[t].iloc[-260:].notna().sum() > 200]
now_ny = dt.datetime.now(ZoneInfo("America/New_York"))
# current prices
px, hl, chg = {}, {}, {}
try:
    lj = json.loads(urllib.request.urlopen("https://raw.githubusercontent.com/sagirozio/wallstreet-he/live/live.json", timeout=30).read().decode())
    if lj.get("date") == now_ny.strftime("%Y-%m-%d"):
        px = {t: v[0] for t, v in lj.get("q", {}).items() if t in mem}
        chg = {t: v[1] for t, v in lj.get("q", {}).items() if t in mem}
        hl = {t: (v[2], v[3]) for t, v in lj.get("q", {}).items() if t in mem and len(v) >= 4}
except Exception as e: print("live.json failed", e)
miss = [t for t in mem if t not in px]
if miss:
    try:
        d = yf.download(miss, period="1d", interval="1d", auto_adjust=False, progress=False, threads=True)["Close"]
        if isinstance(d, pd.Series): d = d.to_frame(miss[0])
        if len(d): px.update({t: float(d[t].iloc[-1]) for t in d.columns if pd.notna(d[t].iloc[-1])})
    except Exception as e: print("yahoo today failed", e)
print("prices", len(px), "of", len(mem), "history to", HIST.index[-1].date())
today = pd.Timestamp(now_ny.date())
# a split / ADR-ratio change between our history and Yahoo's live price: Yahoo's own previous close
# (price / (1 + change)) differs from our last close by >30% -> rescale that stock's history
for t, c in chg.items():
    if t not in px or c is None: continue
    prev_y = px[t] / (1 + c / 100); h = HIST[t].dropna()
    if len(h) and h.index[-1] < today and abs(prev_y / h.iloc[-1] - 1) > 0.3:
        HIST[t] = HIST[t] * (prev_y / h.iloc[-1]); print("rescaled history", t, round(prev_y / h.iloc[-1], 3))
close = HIST[mem]
close = close[close.index < today]
close = pd.concat([close, pd.DataFrame([px], index=[today])]) if len(px) > 0.9 * len(mem) else close
last = close.index[-1]
def ret(n): return (close.iloc[-1] / close.iloc[-1 - n] - 1) * 100
py = close[close.index.year < last.year]
R = {"d": ret(1), "w": ret(5), "m": ret(21), "q": ret(63), "h": ret(126), "y": ret(252), "ytd": (close.iloc[-1] / py.iloc[-1] - 1) * 100}
c = close.iloc[-1]; ma50 = close.rolling(50).mean().iloc[-1]; ma200 = close.rolling(200).mean().iloc[-1]
hi52 = close.iloc[-252:-1].max(); lo52 = close.iloc[-252:-1].min()
# intraday: today's high/low (live.json) vs the 52-week range from daily highs/lows (saved by the nightly update.py)
ref = data.get("hl52") or {}
prev_day = close.index[-2].strftime("%Y-%m-%d") if len(close) > 1 else ""
if last == today and ref.get("d") == prev_day and len(hl) > 0.9 * len(mem):
    dh = pd.Series({t: v[0] for t, v in hl.items()}); dl = pd.Series({t: v[1] for t, v in hl.items()})
    hi_m = dh >= pd.Series(ref["hi"]).reindex(dh.index); lo_m = dl <= pd.Series(ref["lo"]).reindex(dl.index)
    print("52w from intraday highs/lows", int(hi_m.sum()), int(lo_m.sum()))
else:
    hi_m, lo_m = c >= hi52, c <= lo52
    print("52w close-based (no intraday range / reference)", ref.get("d"), prev_day, len(hl))
row = {"d": f"{last.day}.{last.month}", "up": int((R["d"] > 0).sum()), "dn": int((R["d"] < 0).sum()),
       "ma50": round(float((c > ma50)[ma50.notna() & c.notna()].mean() * 100), 1),
       "ma200": round(float((c > ma200)[ma200.notna() & c.notna()].mean() * 100), 1),
       "hi": int(hi_m.sum()), "lo": int(lo_m.sum()),
       "up10": int((R["m"] >= 10).sum()), "dn10": int((R["m"] <= -10).sum())}
def _lst(mask, r, rev=False):
    v = r[mask.reindex(r.index).fillna(False).astype(bool)].dropna().sort_values(ascending=rev)
    return [[t, round(float(x), 1)] for t, x in v.items()]
row["L"] = {"hi": _lst(hi_m, R["d"]), "lo": _lst(lo_m, R["d"], True), "u": _lst(R["m"] >= 10, R["m"]), "n": _lst(R["m"] <= -10, R["m"], True)}
if last == today: row["ma50"] = row["ma200"] = None   # % above the 50 / 200-day average: end of day only (filled by the nightly update.py)
b = data.get("breadth", {"rows": []})
b["rows"] = [row] + [r for r in b.get("rows", []) if r.get("d") != row["d"]][:19]
live = last == today
now_il = dt.datetime.now(ZoneInfo("Asia/Jerusalem"))
stamp = (f"{last.day}.{last.month}.{last.year} בשעה {now_il:%H:%M} (שעון ישראל)" if live else f"סגירת {last.day}.{last.month}.{last.year}")
b["asOf"] = stamp; data["breadth"] = b
GICS = {"Information Technology": "XLK", "Communication Services": "XLC", "Consumer Discretionary": "XLY", "Consumer Staples": "XLP", "Energy": "XLE",
        "Financials": "XLF", "Health Care": "XLV", "Industrials": "XLI", "Real Estate": "XLRE", "Materials": "XLB", "Utilities": "XLU"}
sec_of = dict(zip(sp["yf"], sp["GICS Sector"]))
for srow in data["sectors"]["rows"]:
    g = [k for k, v in GICS.items() if v == srow["t"]]
    if not g: continue
    m = [t for t in mem if sec_of.get(t) == g[0]]
    for k, s in R.items():
        v = s.reindex(m).dropna()
        if len(v): srow[k] = round(float(v.mean()), 2)
import sys as _sys; _sys.path.insert(0, str(root / "scripts"))
import sector_etf
_etf_ok = sector_etf.apply(data)   # the sector ETF's own price change, like Google Finance / TradingView
data["sectors"]["asOf"] = (f"{last.day}.{last.month}.{last.year} בשעה {now_il:%H:%M} (שעון ישראל)" if live else stamp) + (" · שינוי המחיר של קרן הסל של כל סקטור" if _etf_ok else " · ממוצע מניות ה-S&P 500 בכל סקטור")
p.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
print("breadth", row)
# movers (same as update.py)
subprocess.call([sys.executable, str(root / "scripts" / "movers.py")])
