"""Short interest for every stock on the site, from Yahoo (it comes from the exchanges' twice-a-month report).

Writes into facts.json per ticker:  si = short interest as % of the float,  sr = days to cover (short ratio),
sid = the date of the exchange report.  Slow on purpose (Yahoo throttles): ~0.6 s per stock, oldest first.
"""
import json, sys, time, pathlib, datetime as dt
import yfinance as yf

root = pathlib.Path(__file__).resolve().parent.parent
data = json.loads((root / "data.json").read_text(encoding="utf-8"))
facts_p = root / "facts.json"
facts = json.loads(facts_p.read_text(encoding="utf-8")) if facts_p.exists() else {}
tick = [s[0] for lst in (data.get("themes", {}).get("stocks") or {}).values() for s in lst]
# stocks never fetched first, then the oldest
tick.sort(key=lambda t: (facts.get(t) or {}).get("siAt", ""))
MIN = float(sys.argv[1]) if len(sys.argv) > 1 else 45     # minutes budget
end = time.time() + MIN * 60
today = dt.date.today().isoformat()
done = fails = 0
for t in tick:
    if time.time() > end: break
    try: info = yf.Ticker(t).info or {}
    except Exception as e:
        fails += 1; print("fail", t, type(e).__name__, flush=True)
        if fails >= 25: print("too many failures, stopping"); break
        time.sleep(5); continue
    f = facts.setdefault(t, {})
    p = info.get("shortPercentOfFloat")
    if isinstance(p, (int, float)) and 0 <= p < 2: f["si"] = round(p * 100, 1)
    else: f.pop("si", None)
    r = info.get("shortRatio")
    if isinstance(r, (int, float)) and r >= 0: f["sr"] = round(r, 1)
    else: f.pop("sr", None)
    d = info.get("dateShortInterest")
    if isinstance(d, (int, float)) and d > 0: f["sid"] = dt.datetime.utcfromtimestamp(d).date().isoformat()
    f["siAt"] = today
    done += 1
    if done % 200 == 0:
        print(done, t, flush=True); facts_p.write_text(json.dumps(facts, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    time.sleep(0.6)
facts_p.write_text(json.dumps(facts, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
print("done", done, "fails", fails, "with si", sum(1 for t in tick if "si" in (facts.get(t) or {})))
