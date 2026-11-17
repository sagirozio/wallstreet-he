"""Weekly earnings calendar, automatic (Finnhub /calendar/earnings, free tier; key in the FINNHUB_KEY secret).
Week: Mon–Fri of the current New York week (Saturday/Sunday -> next week).
Per day: the largest reporting companies of our universe (cap >= $1B, liquid), EPS / revenue estimates, before open / after close.
Hand-written fields (n, at, star, il, econ) and hand-added items of the same week are kept. Writes data.json["calendar"]."""
import json, os, re, pathlib, urllib.request, urllib.parse, datetime as dt
from zoneinfo import ZoneInfo
KEY = os.environ.get("FINNHUB_KEY", "").strip()
if not KEY: raise SystemExit("FINNHUB_KEY missing")
PER_DAY = 12
IL = {"TEVA", "CHKP", "NICE", "WIX", "MNDY", "CYBR", "GLBE", "ESLT", "INMD", "SEDG", "ORA", "NVMI", "CAMT", "TSEM", "FVRR", "SPNS", "KRNT", "PAYO", "OUST", "ICL", "LMND", "ZIM", "TARO", "CLBT", "SMWB", "ITRN", "HOLO", "ODD", "NNOX", "RDWR", "SLGN"}
root = pathlib.Path(__file__).resolve().parent.parent
p = root / "data.json"; d = json.loads(p.read_text(encoding="utf-8"))
def cap(s):
    m = re.fullmatch(r"([\d.]+)([TBM])", str(s or "")); return float(m[1]) * {"T": 1e12, "B": 1e9, "M": 1e6}[m[2]] if m else 0
U = {}
for lst in d.get("themes", {}).get("stocks", {}).values():
    for s in lst: U[s[0]] = (s[1], cap(s[2]))
ny = dt.datetime.now(ZoneInfo("America/New_York")).date()
mon = ny - dt.timedelta(days=ny.weekday()) + (dt.timedelta(days=7) if ny.weekday() >= 5 else dt.timedelta())
fri = mon + dt.timedelta(days=4)
url = "https://finnhub.io/api/v1/calendar/earnings?" + urllib.parse.urlencode({"from": mon.isoformat(), "to": fri.isoformat(), "token": KEY})
rows = json.loads(urllib.request.urlopen(url, timeout=60).read().decode()).get("earningsCalendar") or []
print("finnhub rows", len(rows), mon, fri)
# a company listed on two days (estimated + confirmed dates): keep one — Yahoo's date if it matches, else the earliest
ED = d.get("earnDates") or {}
by = {}
for r in rows: by.setdefault(r.get("symbol"), []).append(r)
rows = []
for sym, rs in by.items():
    rs.sort(key=lambda r: r.get("date") or "")
    y = str((ED.get((sym or "").replace(".", "-")) or {}).get("d") or "")[:10]
    rows.append(next((r for r in rs if r.get("date") == y), rs[0]))
week = f"{mon.day}–{fri.day}.{fri.month}.{fri.year}" if mon.month == fri.month else f"{mon.day}.{mon.month}–{fri.day}.{fri.month}.{fri.year}"
old = d.get("calendar") or {}
same = old.get("week") == week
oldi = {}
if same:
    for day in old.get("days", []):
        for it in day.get("items", []): oldi[(day["d"], it["t"])] = it
HE = ["שני", "שלישי", "רביעי", "חמישי", "שישי"]
days = []
for i in range(5):
    day = mon + dt.timedelta(days=i); lbl = f"{HE[i]} {day.day}.{day.month}"
    got = {}
    for r in rows:
        if r.get("date") != day.isoformat(): continue
        t = (r.get("symbol") or "").replace(".", "-")
        if t not in U: continue
        h = {"bmo": "bmo", "amc": "amc"}.get(r.get("hour") or "", "")
        it = {"t": t, "co": U[t][0], "time": h or "amc", "star": False, "a": 1}   # a = added automatically
        if r.get("epsEstimate") is not None: it["eps"] = round(float(r["epsEstimate"]), 2)
        if r.get("revenueEstimate"): it["rev"] = round(float(r["revenueEstimate"]) / 1e9, 2)
        if t in IL: it["il"] = True
        got[t] = it
    top = sorted(got.values(), key=lambda x: -U[x["t"]][1])[:PER_DAY]
    keep = {t for (dl, t), o in oldi.items() if dl == lbl and not o.get("a")}   # hand-placed items stay
    top += [got[t] for t in keep if t in got and got[t] not in top]
    items = []
    for it in top:
        o = oldi.get((lbl, it["t"]), {})
        items.append({**it, **{k: v for k, v in o.items() if k in ("n", "at", "star", "il", "co", "time") and v not in (None, "")}})
    # hand-added items Finnhub doesn't list
    items += [o for (dl, t), o in oldi.items() if dl == lbl and t not in got and not o.get("a")]
    items.sort(key=lambda x: (x.get("time") != "bmo", -U.get(x["t"], ("", 0))[1]))
    econ = next((x.get("econ", "") for x in old.get("days", []) if same and x.get("d") == lbl), "")
    days.append({"d": lbl, "items": items, "econ": econ})
new = {"week": week,
       "note": "החברות הגדולות שמדווחות השבוע (שווי שוק מעל מיליארד דולר), לפי Finnhub, עם תחזיות האנליסטים. 🇮🇱 = חברה ישראלית. השעות לפי שעון ניו יורק (ET), בישראל זה 7 שעות מאוחר יותר.",
       "days": days}
if {k: v for k, v in old.items() if k != "rev"} != new:
    new["rev"] = int(dt.datetime.now(ZoneInfo("Asia/Jerusalem")).strftime("%Y%m%d%H%M"))
    d["calendar"] = new
    p.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
print("calendar", week, [len(x["items"]) for x in days])
