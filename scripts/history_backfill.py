"""One-off: build ~14 months of daily closes from Massive for every stock on the site + S&P 500 members (~60–70 min)."""
import json, pathlib, io, urllib.request, pandas as pd
import hist
root = pathlib.Path(__file__).resolve().parent.parent
d = json.loads((root / "data.json").read_text(encoding="utf-8"))
keep = {s[0] for l in d["themes"]["stocks"].values() for s in l}
try:
    sp = pd.read_csv(io.StringIO(urllib.request.urlopen("https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv", timeout=60).read().decode()))
    keep |= set(sp["Symbol"].str.replace(".", "-", regex=False))
except Exception as e: print("spx list failed", e)
for e in ("SPY", "QQQ", "DIA", "IWM", "XLK", "XLC", "XLY", "XLP", "XLE", "XLF", "XLV", "XLI", "XLRE", "XLB", "XLU"): keep.add(e)
df, rep = hist.update(pd.DataFrame(), keep)
print("sessions", len(rep["added"]), "tickers", df.shape[1])
hist.save(df)
