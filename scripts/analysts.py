"""Analyst data from Finnhub (free tier) -> analysts.json
- rec:  recommendation trends per stock: [strongBuy, buy, hold, sell, strongSell] now and ~3 months ago
- next: consensus for the next report (date, EPS and revenue estimates) from the earnings calendar, 100 days ahead
Weekly (analysts.yml); ~35 minutes for the whole universe at 1 call/second. Facts with attribution, not our recommendation."""
import json, os, sys, time, pathlib, urllib.request, urllib.parse, datetime as dt
KEY = os.environ.get("FINNHUB_KEY", "").strip()
if not KEY: raise SystemExit("FINNHUB_KEY missing")
root = pathlib.Path(__file__).resolve().parent.parent
d = json.loads((root / "data.json").read_text(encoding="utf-8"))
import re
def cap(s):
    m = re.fullmatch(r"([\d.]+)([TBM])", str(s or "")); return float(m[1]) * {"T": 1e12, "B": 1e9, "M": 1e6}[m[2]] if m else 0
U = {s[0]: cap(s[2]) for l in d["themes"]["stocks"].values() for s in l}
out_p = root / "analysts.json"
try: out = json.loads(out_p.read_text(encoding="utf-8"))
except Exception: out = {}
rec = out.get("rec", {}); last = [0.0]
def get(path, **q):
    for k in range(3):
        w = 1.08 - (time.time() - last[0])
        if w > 0: time.sleep(w)
        last[0] = time.time()
        try:
            with urllib.request.urlopen("https://finnhub.io/api/v1/" + path + "?" + urllib.parse.urlencode({**q, "token": KEY}), timeout=20) as r:
                return json.loads(r.read().decode())
        except Exception as e:
            if "429" in str(e): time.sleep(20)
            elif "403" in str(e): return None
            else: time.sleep(3)
    return None
# next report consensus (4 calls)
nxt = {}; today = dt.date.today()
for i in range(4):
    a = today + dt.timedelta(days=i * 25); b = a + dt.timedelta(days=24)
    for r in (get("calendar/earnings", **{"from": a.isoformat(), "to": b.isoformat()}) or {}).get("earningsCalendar") or []:
        t = (r.get("symbol") or "").replace(".", "-")
        if t not in U or not r.get("date") or t in nxt and nxt[t]["d"] <= r["date"]: continue
        x = {"d": r["date"], "h": r.get("hour") or ""}
        if r.get("epsEstimate") is not None: x["eps"] = round(float(r["epsEstimate"]), 2)
        if r.get("revenueEstimate"): x["rev"] = round(float(r["revenueEstimate"]) / 1e9, 3)
        if r.get("quarter"): x["q"] = f"Q{r['quarter']} {r.get('year', '')}".strip()
        nxt[t] = x
print("next reports", len(nxt), flush=True)
# recommendation trends, largest companies first; stop after the time budget (the rest keeps last week's values)
budget = int(sys.argv[1]) * 60 if len(sys.argv) > 1 else 45 * 60; t0 = time.time(); n = 0
for t in sorted(U, key=lambda t: -U[t]):
    if time.time() - t0 > budget: break
    j = get("stock/recommendation", symbol=t.replace("-", "."))
    if not isinstance(j, list) or not j: continue
    j.sort(key=lambda x: x.get("period", ""), reverse=True)
    f = lambda x: [x.get("strongBuy", 0), x.get("buy", 0), x.get("hold", 0), x.get("sell", 0), x.get("strongSell", 0)]
    if sum(f(j[0])) < 1: continue
    rec[t] = {"p": j[0].get("period", "")[:7], "now": f(j[0])}
    if len(j) > 3 and sum(f(j[3])): rec[t]["old"] = f(j[3])
    n += 1
    if n % 200 == 0: print("rec", n, flush=True)
out = {"asOf": today.isoformat(), "rec": {t: v for t, v in rec.items() if t in U}, "next": nxt}
out_p.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
print("analysts: rec", len(out["rec"]), "updated", n, "next", len(nxt))
