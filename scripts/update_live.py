"""Intraday (every 10 min in the session), light: sectors + breadth from our close history + current prices.
Current prices: live.json (Yahoo screener, refreshed every 5 min by live.yml); missing tickers -> one small Yahoo download.
52-week highs/lows here are close-based (the nightly update.py recomputes them from intraday highs/lows).
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
px = {}
try:
    lj = json.loads(urllib.request.urlopen("https://raw.githubusercontent.com/sagirozio/wallstreet-he/live/live.json", timeout=30).read().decode())
    if lj.get("date") == now_ny.strftime("%Y-%m-%d"):
        px = {t: v[0] for t, v in lj.get("q", {}).items() if t in mem}
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
close = HIST[mem]
close = close[close.index < today]
close = pd.concat([close, pd.DataFrame([px], index=[today])]) if len(px) > 0.9 * len(mem) else close
last = close.index[-1]
def ret(n): return (close.iloc[-1] / close.iloc[-1 - n] - 1) * 100
py = close[close.index.year < last.year]
R = {"d": ret(1), "w": ret(5), "m": ret(21), "q": ret(63), "h": ret(126), "y": ret(252), "ytd": (close.iloc[-1] / py.iloc[-1] - 1) * 100}
c = close.iloc[-1]; ma50 = close.rolling(50).mean().iloc[-1]; ma200 = close.rolling(200).mean().iloc[-1]
hi52 = close.iloc[-252:-1].max(); lo52 = close.iloc[-252:-1].min()
row = {"d": f"{last.day}.{last.month}", "up": int((R["d"] > 0).sum()), "dn": int((R["d"] < 0).sum()),
       "ma50": round(float((c > ma50)[ma50.notna() & c.notna()].mean() * 100), 1),
       "ma200": round(float((c > ma200)[ma200.notna() & c.notna()].mean() * 100), 1),
       "hi": int((c >= hi52).sum()), "lo": int((c <= lo52).sum()),
       "up10": int((R["m"] >= 10).sum()), "dn10": int((R["m"] <= -10).sum())}
def _lst(mask, r, rev=False):
    v = r[mask.reindex(r.index).fillna(False).astype(bool)].dropna().sort_values(ascending=rev)
    return [[t, round(float(x), 1)] for t, x in v.items()]
row["L"] = {"hi": _lst(c >= hi52, R["d"]), "lo": _lst(c <= lo52, R["d"], True), "u": _lst(R["m"] >= 10, R["m"]), "n": _lst(R["m"] <= -10, R["m"], True)}
b = data.get("breadth", {"rows": []})
b["rows"] = [row] + [r for r in b.get("rows", []) if r.get("d") != row["d"]][:19]
live = last == today
now_il = dt.datetime.now(ZoneInfo("Asia/Jerusalem"))
stamp = (f"{last.day}.{last.month}.{last.year} בשעה {now_il:%H:%M} (שעון ישראל, בעיכוב של כ-15 דקות)" if live else f"סגירת {last.day}.{last.month}.{last.year}")
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
data["sectors"]["asOf"] = stamp + " · ממוצע מניות ה-S&P 500 בכל סקטור"
p.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
print("breadth", row)
# movers (same as update.py)
subprocess.call([sys.executable, str(root / "scripts" / "movers.py")])
