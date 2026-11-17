"""Company background for the stock pages.

For every stock on the site (themes.stocks) that we don't have yet, fetch from Yahoo:
  - facts shown on the page: headquarters, employees, website      -> data.json["facts"]
  - Yahoo's English business summary, used ONLY as research material
    for the Hebrew "about" paragraphs the scheduled runs write       -> about_src.json (not shown on the site)
Slow on purpose (Yahoo throttles); fills in over a few runs.
"""
import json, sys, time, pathlib
import yfinance as yf

root = pathlib.Path(__file__).resolve().parent.parent
data = json.loads((root / "data.json").read_text(encoding="utf-8"))
src_p = root / "about_src.json"
src = json.loads(src_p.read_text(encoding="utf-8")) if src_p.exists() else {}
facts = data.get("facts", {})

tick = []
for lst in (data.get("themes", {}).get("stocks") or {}).values():
    for s in lst: tick.append((s[0], s[2]))
def capv(c):
    try: return float(c[:-1]) * (1e12 if c.endswith("T") else 1e9)
    except Exception: return 0
tick = [t for t, c in sorted(tick, key=lambda x: -capv(x[1])) if t not in src]
LIMIT = int(sys.argv[1]) if len(sys.argv) > 1 else 700
print("missing", len(tick), "fetching up to", LIMIT, flush=True)

done = fails = 0
for t in tick[:LIMIT]:
    try:
        info = yf.Ticker(t).info or {}
    except Exception as e:
        fails += 1; print("fail", t, type(e).__name__, flush=True)
        if fails >= 25: print("too many failures, stopping"); break
        time.sleep(5); continue
    hq = ", ".join(x for x in [info.get("city"), info.get("state") if info.get("country") == "United States" else None, info.get("country")] if x)
    src[t] = {"summary": info.get("longBusinessSummary", ""), "name": info.get("longName") or info.get("shortName") or t}
    f = {}
    if hq: f["hq"] = hq
    if info.get("fullTimeEmployees"): f["emp"] = int(info["fullTimeEmployees"])
    if info.get("website"): f["web"] = info["website"]
    if f: facts[t] = f
    done += 1
    if done % 100 == 0:
        print(done, t, flush=True)
        src_p.write_text(json.dumps(src, ensure_ascii=False, indent=0), encoding="utf-8")
    time.sleep(0.8)

src_p.write_text(json.dumps(src, ensure_ascii=False, indent=0), encoding="utf-8")
data["facts"] = facts
(root / "data.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
print("done", done, "fails", fails, "total src", len(src), "facts", len(facts))
