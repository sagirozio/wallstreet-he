"""Same-day basic earnings cards from Finnhub (Yahoo's statements lag a day or more).
For every company in our universe that reported today or yesterday (New York) and already has an actual EPS on Finnhub,
add an `auto` card: EPS vs estimate, revenue vs estimate, and the stock's move (live.json). Claude runs enrich them later."""
import json, os, re, pathlib, urllib.request, urllib.parse, datetime as dt
from zoneinfo import ZoneInfo
KEY = os.environ.get("FINNHUB_KEY", "").strip()
if not KEY: raise SystemExit("FINNHUB_KEY missing")
root = pathlib.Path(__file__).resolve().parent.parent
p = root / "data.json"; d = json.loads(p.read_text(encoding="utf-8"))
U = {s[0]: s[1] for lst in d.get("themes", {}).get("stocks", {}).values() for s in lst}
SEC = {}
for r in d.get("reports", []):
    if r.get("sector"): SEC[r["t"]] = r["sector"]
ny = dt.datetime.now(ZoneInfo("America/New_York")).date()
a = ny - dt.timedelta(days=3 if ny.weekday() == 0 else 1)
url = "https://finnhub.io/api/v1/calendar/earnings?" + urllib.parse.urlencode({"from": a.isoformat(), "to": ny.isoformat(), "token": KEY})
rows = json.loads(urllib.request.urlopen(url, timeout=60).read().decode()).get("earningsCalendar") or []
try: LQ = json.loads(urllib.request.urlopen("https://raw.githubusercontent.com/sagirozio/wallstreet-he/live/live.json", timeout=30).read().decode())
except Exception: LQ = {}
have = {r["id"] for r in d["reports"]}; added = 0
for r in rows:
    t = (r.get("symbol") or "").replace(".", "-")
    if t not in U or r.get("epsActual") is None: continue
    day = dt.date.fromisoformat(r["date"])
    cid = f"{t}-{day:%Y-%m}"
    if cid in have: continue
    q = f"Q{r.get('quarter')} {r.get('year')}" if r.get("quarter") else ""
    react = ""
    lq = (LQ.get("q") or {}).get(t)
    amc = r.get("hour") == "amc"
    if lq and LQ.get("date") == ny.isoformat() and ((not amc and day == ny) or (amc and day < ny)):
        ch = lq[1]; react = f"המניה {'עולה' if ch >= 0 else 'יורדת'} ב-{abs(ch):.1f}% במסחר היום (נכון ל-{LQ.get('asOf', '').split('·')[-1].strip()})."
    card = {"id": cid, "t": t, "co": U[t], "sector": SEC.get(t, ""), "date": day.isoformat(), "q": q,
            "epsAct": round(float(r["epsActual"]), 2), "epsEst": round(float(r["epsEstimate"]), 2) if r.get("epsEstimate") is not None else None,
            "epsYoy": None, "epsBasis": "מתואם",
            "revAct": round(r["revenueActual"] / 1e9, 4) if r.get("revenueActual") else None,
            "revEst": round(r["revenueEstimate"] / 1e9, 4) if r.get("revenueEstimate") else None, "revYoy": None,
            "guide": "none", "guideText": "", "note": "", "react": react,
            "ir": f"https://www.earningswhispers.com/epsdetails/{t}", "hook": "", "auto": True, "src": "finnhub"}
    d["reports"].append(card); have.add(cid); added += 1
    print("added", t, day, card["epsAct"], card["epsEst"], card["revAct"], card["revEst"], react, flush=True)
# refresh the reaction line of today's finnhub cards
for c in d["reports"]:
    if c.get("src") == "finnhub" and c.get("auto") and c["date"] == ny.isoformat():
        lq = (LQ.get("q") or {}).get(c["t"])
        if lq and LQ.get("date") == ny.isoformat() and not c.get("note"):
            c["react"] = f"המניה {'עולה' if lq[1] >= 0 else 'יורדת'} ב-{abs(lq[1]):.1f}% במסחר היום (נכון ל-{LQ.get('asOf', '').split('·')[-1].strip()})."
d["reports"].sort(key=lambda r: str(r.get("date", "")), reverse=True)
p.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
print("added", added)
