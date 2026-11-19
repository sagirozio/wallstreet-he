"""Past earnings report dates per stock (Yahoo), for the report dots on the stock page chart.

Writes earndates.json = {asOf, d: {T: ["YYYY-MM-DD", ...]}}  (newest first, past reports only, up to 8).
Slow on purpose (Yahoo throttles): oldest-fetched first, within a minutes budget.
"""
import json, sys, time, pathlib, datetime as dt
import yfinance as yf

root = pathlib.Path(__file__).resolve().parent.parent
data = json.loads((root / "data.json").read_text(encoding="utf-8"))
p = root / "earndates.json"
out = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
D, AT = out.setdefault("d", {}), out.setdefault("at", {})
tick = [s[0] for l in (data.get("themes", {}).get("stocks") or {}).values() for s in l]
tick.sort(key=lambda t: AT.get(t, ""))
MIN = float(sys.argv[1]) if len(sys.argv) > 1 else 45
end = time.time() + MIN * 60
today = dt.date.today()
done = fails = 0
for t in tick:
    if time.time() > end: break
    try:
        ed = yf.Ticker(t).get_earnings_dates(limit=12)
    except Exception as e:
        fails += 1; print("fail", t, type(e).__name__, flush=True)
        if fails >= 25: print("too many failures, stopping"); break
        time.sleep(4); continue
    ds = []
    if ed is not None and len(ed):
        for ts, row in ed.iterrows():
            d = ts.tz_convert("America/New_York") if getattr(ts, "tzinfo", None) else ts
            # after the close (16:00 NY or later) the market reacts the next session: store that day
            day = d.date() + dt.timedelta(days=1) if d.hour >= 16 else d.date()
            while day.weekday() >= 5: day += dt.timedelta(days=1)
            if d.date() <= today and str(row.get("Reported EPS")) != "nan": ds.append(day.isoformat())
    D[t] = sorted(set(ds), reverse=True)[:8]
    AT[t] = today.isoformat()
    done += 1
    if done % 200 == 0:
        print(done, t, flush=True); out["asOf"] = today.isoformat(); p.write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    time.sleep(0.5)
out["asOf"] = today.isoformat()
p.write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
print("done", done, "fails", fails, "with dates", sum(1 for t in tick if D.get(t)))
