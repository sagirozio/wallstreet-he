"""Fill missing estimates from Finnhub (free tier, 60 calls/min; key in the FINNHUB_KEY secret).
- auto earnings cards: revenue estimate (and actual revenue when missing), EPS estimate when missing
- this week's earnings calendar: EPS / revenue estimates for items that have none
"""
import json, os, pathlib, time, urllib.request, urllib.parse, datetime as dt

KEY = os.environ.get("FINNHUB_KEY", "").strip()
if not KEY: raise SystemExit("FINNHUB_KEY missing")
root = pathlib.Path(__file__).resolve().parent.parent
p = root / "data.json"; d = json.loads(p.read_text(encoding="utf-8"))
last = [0.0]
def api(path, **q):
    wait = 1.05 - (time.time() - last[0])
    if wait > 0: time.sleep(wait)
    q["token"] = KEY; last[0] = time.time()
    url = f"https://finnhub.io/api/v1/{path}?{urllib.parse.urlencode(q)}"
    for k in range(3):
        try:
            with urllib.request.urlopen(url, timeout=20) as r: return json.loads(r.read().decode())
        except Exception as e:
            if "429" in str(e): time.sleep(20)
            else: time.sleep(2)
    return {}

def cal(sym, day):
    a = (day - dt.timedelta(days=3)).isoformat(); b = (day + dt.timedelta(days=3)).isoformat()
    rows = (api("calendar/earnings", **{"from": a, "to": b, "symbol": sym.replace("-", ".")}) or {}).get("earningsCalendar") or []
    return min(rows, key=lambda r: abs((dt.date.fromisoformat(r["date"]) - day).days)) if rows else None

n = 0; todo = [r for r in d["reports"] if r.get("auto") and not r.get("revCur") and (r.get("revEst") is None or r.get("epsEst") is None)]
print("auto cards", len(todo), flush=True)
for r in todo:
    try: x = cal(r["t"], dt.date.fromisoformat(r["date"]))
    except Exception as e: print(r["t"], "err", e); continue
    if not x: continue
    ch = False
    if not r.get("revCur") and r.get("_usd", True):
        if r.get("revEst") is None and x.get("revenueEstimate"): r["revEst"] = round(x["revenueEstimate"] / 1e9, 4); ch = True
        if r.get("revAct") is None and x.get("revenueActual"): r["revAct"] = round(x["revenueActual"] / 1e9, 4); ch = True
    if r.get("epsEst") is None and x.get("epsEstimate") is not None: r["epsEst"] = round(x["epsEstimate"], 2); ch = True
    if ch: n += 1
print("cards filled", n, flush=True)

m = 0; C = d.get("calendar") or {}
yr = dt.date.today().year
for day in C.get("days", []):
    import re
    mm = re.search(r"(\d{1,2})\.(\d{1,2})", day.get("d", ""))
    if not mm: continue
    dd = dt.date(yr, int(mm[2]), int(mm[1]))
    for i in day.get("items", []):
        if isinstance(i.get("eps"), (int, float)) and isinstance(i.get("rev"), (int, float)): continue
        x = cal(i["t"], dd)
        if not x: continue
        if not isinstance(i.get("eps"), (int, float)) and x.get("epsEstimate") is not None: i["eps"] = round(x["epsEstimate"], 2); m += 1
        if not isinstance(i.get("rev"), (int, float)) and x.get("revenueEstimate"): i["rev"] = round(x["revenueEstimate"] / 1e9, 2)
print("calendar items filled", m)
p.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
