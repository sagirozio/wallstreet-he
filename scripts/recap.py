"""Daily recap after the US close -> data.json["recap"] (built from tables we already compute; runs in the nightly update).
Indices (Yahoo), sectors (best / worst today), industries (best / worst today, 3+ stocks), today's 10%+ movers both ways,
breadth (advancers / decliners, new 52-week highs / lows with names)."""
import json, pathlib, datetime as dt
from zoneinfo import ZoneInfo
import yfinance as yf
root = pathlib.Path(__file__).resolve().parent.parent
p = root / "data.json"; d = json.loads(p.read_text(encoding="utf-8"))
ix = []
for sym, n in (("^GSPC", "S&P 500"), ("^IXIC", "נאסד״ק"), ("^DJI", "דאו ג׳ונס"), ("^RUT", "ראסל 2000")):
    try:
        c = yf.download(sym, period="5d", interval="1d", progress=False, auto_adjust=False)["Close"].dropna()
        c = c.iloc[:, 0] if hasattr(c, "columns") else c
        ny = dt.datetime.now(ZoneInfo("America/New_York"))
        if c.index[-1].date() == ny.date() and ny.hour * 60 + ny.minute < 16 * 60 + 5: c = c.iloc[:-1]   # session still open: last complete day
        ix.append({"n": n, "v": round(float(c.iloc[-1]), 2), "c": round(float((c.iloc[-1] / c.iloc[-2] - 1) * 100), 2)}); day = c.index[-1].date()
    except Exception as e: print("index", sym, e)
if not ix: raise SystemExit("no index data")
sec = sorted([r for r in d.get("sectors", {}).get("rows", []) if r.get("d") is not None], key=lambda r: -r["d"])
T = d.get("themes", {}); st = T.get("stocks", {})
ind = sorted([r for r in T.get("rows", []) if r.get("d") is not None and len(st.get(r["en"], [])) >= 3], key=lambda r: -r["d"])
def top_stocks(en, k=3, rev=False):
    l = [s for s in st.get(en, []) if isinstance(s[3], dict) and s[3].get("d") is not None]
    l.sort(key=lambda s: s[3]["d"], reverse=not rev); return [[s[0], round(s[3]["d"], 1)] for s in l[:k]]
mv = d.get("movers", {}); b = (d.get("breadth", {}).get("rows") or [{}])[0]; L = b.get("L") or {}
recap = {"date": day.isoformat(), "asOf": f"סגירת {day.day}.{day.month}.{day.year}", "idx": ix,
         "secTop": [{"n": r["name"], "t": r.get("t"), "c": r["d"]} for r in sec[:3]],
         "secBot": [{"n": r["name"], "t": r.get("t"), "c": r["d"]} for r in sec[-3:][::-1]],
         "indTop": [{"n": r["n"], "en": r["en"], "c": r["d"], "s": top_stocks(r["en"])} for r in ind[:5]],
         "indBot": [{"n": r["n"], "en": r["en"], "c": r["d"], "s": top_stocks(r["en"], rev=True)} for r in ind[-5:][::-1]],
         "up": [] if mv.get("pre") else (mv.get("rows") or [])[:10], "down": [] if mv.get("pre") else (mv.get("down") or [])[:10],
         "breadth": {"up": b.get("up"), "dn": b.get("dn"), "hi": L.get("hi", [])[:12], "lo": L.get("lo", [])[:12], "nhi": b.get("hi"), "nlo": b.get("lo")}}
d["recap"] = recap
p.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
print("recap", recap["asOf"], [(x["n"], x["c"]) for x in ix])
