"""One-off / manual: rebuild the breadth table for the last N trading days (default 20)
with exactly the same definitions as update.py, from Yahoo daily history of the current S&P 500 members."""
import json, pathlib, io, sys, urllib.request
import pandas as pd, yfinance as yf

N = int(sys.argv[1]) if len(sys.argv) > 1 else 20
root = pathlib.Path(__file__).resolve().parent.parent
p = root / "data.json"; data = json.loads(p.read_text(encoding="utf-8"))
CSV = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"
sp = pd.read_csv(io.StringIO(urllib.request.urlopen(CSV, timeout=60).read().decode()))
tickers = sp["Symbol"].str.replace(".", "-", regex=False).tolist()
px = yf.download(tickers, period="2y", interval="1d", auto_adjust=True, group_by="column", threads=True, progress=False)
close, high, low = px["Close"].dropna(how="all"), px["High"], px["Low"]
good = [c for c in close.columns if close[c].notna().sum() > 200]
close, high, low = close[good], high.reindex(close.index)[good], low.reindex(close.index)[good]
# drop a sparse last row (partial / missing data)
if close.iloc[-1].notna().mean() < 0.9: close, high, low = close.iloc[:-1], high.iloc[:-1], low.iloc[:-1]
ma50, ma200 = close.rolling(50).mean(), close.rolling(200).mean()
hi52 = high.shift(1).rolling(251, min_periods=200).max(); lo52 = low.shift(1).rolling(251, min_periods=200).min()
rows = []
for i in range(len(close) - 1, len(close) - 1 - N, -1):
    d = close.index[i]; c = close.iloc[i]
    r1 = (c / close.iloc[i - 1] - 1) * 100; r21 = (c / close.iloc[i - 21] - 1) * 100
    m50, m200 = ma50.iloc[i], ma200.iloc[i]
    def _lst(mask, r, rev=False):
        v = r[mask.reindex(r.index).fillna(False).astype(bool)].dropna().sort_values(ascending=rev)
        return [[t, round(float(x), 1)] for t, x in v.items()]
    L = {"hi": _lst(high.iloc[i] >= hi52.iloc[i], r1), "lo": _lst(low.iloc[i] <= lo52.iloc[i], r1, True),
         "u": _lst(r21 >= 10, r21), "n": _lst(r21 <= -10, r21, True)}
    rows.append({"L": L, "d": f"{d.day}.{d.month}",
        "up": int((r1 > 0).sum()), "dn": int((r1 < 0).sum()),
        "ma50": round(float((c > m50)[m50.notna() & c.notna()].mean() * 100), 1),
        "ma200": round(float((c > m200)[m200.notna() & c.notna()].mean() * 100), 1),
        "hi": int((high.iloc[i] >= hi52.iloc[i]).sum()), "lo": int((low.iloc[i] <= lo52.iloc[i]).sum()),
        "up10": int((r21 >= 10).sum()), "dn10": int((r21 <= -10).sum())})
last = close.index[-1]
data["breadth"] = {**data.get("breadth", {}), "rows": rows, "asOf": f"סגירת {last.day}.{last.month}.{last.year}"}
p.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
print("breadth rows", len(rows), rows[:3])
