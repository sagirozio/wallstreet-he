"""Check this week's earnings calendar against SEC: the results 8-K (Item 2.02) the company filed.

For every company on a day that has already started (New York time): its EDGAR submissions are read, and an 8-K with
Item 2.02 filed within 4 days of the listed date gives the real date and time. acceptanceDateTime in EDGAR's JSON is
Eastern time (the trailing Z is not UTC: a filing accepted after 17:30 gets the next filingDate).
  before 9:30 ET  -> before the open (bmo), that day
  from 16:00 ET   -> after the close (amc), that day
  in between      -> the date is fixed, the time stays as listed (the release may have come before the filing)
A company found on another day of the week is moved there. Verified items get "sec": 1.
Runs after calendar_auto.py. Fail-soft: any error leaves the calendar as it was."""
import json, os, re, pathlib, time, gzip, urllib.request, datetime as dt
from zoneinfo import ZoneInfo

UA = " ".join(re.sub(r"[^\x20-\x7e]", " ", os.environ.get("SEC_UA") or "").split()) or "Wallstreeter bot@users.noreply.github.com"
root = pathlib.Path(__file__).resolve().parent.parent
p = root / "data.json"; d = json.loads(p.read_text(encoding="utf-8"))
cal = d.get("calendar") or {}
if not cal.get("days"): raise SystemExit("no calendar")

def get(url):
    for k in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "gzip"})
            with urllib.request.urlopen(req, timeout=30) as r:
                b = r.read()
                if b[:2] == b"\x1f\x8b": b = gzip.decompress(b)
                return json.loads(b)
        except Exception as e:
            print("sec", type(e).__name__, flush=True); time.sleep(2 + 3 * k)
    return None

ny = dt.datetime.now(ZoneInfo("America/New_York"))
yr = ny.year
def day_date(lbl):                       # "שלישי 24.11" -> date (the week can cross a year end)
    m = re.search(r"(\d+)\.(\d+)", lbl); dd, mm = int(m[1]), int(m[2])
    y = yr - 1 if (mm == 12 and ny.month == 1) else yr + 1 if (mm == 1 and ny.month == 12) else yr
    return dt.date(y, mm, dd)
days = [(x, day_date(x["d"])) for x in cal["days"]]
todo = [(x, dd, it) for x, dd in days if dd <= ny.date() for it in x["items"] if not it.get("sec")]
print("to check", len(todo), flush=True)
if not todo: raise SystemExit(0)

tk = get("https://www.sec.gov/files/company_tickers.json") or {}
CIK = {str(v.get("ticker", "")).upper().replace(".", "-"): int(v.get("cik_str") or 0) for v in tk.values()}
moves, fixed, checked = [], 0, 0
for x, dd, it in todo:
    c = CIK.get(it["t"])
    if not c: continue
    j = get(f"https://data.sec.gov/submissions/CIK{c:010d}.json"); time.sleep(0.15)   # SEC asks for <= 10 requests a second
    if not j: continue
    checked += 1
    r = j.get("filings", {}).get("recent", {})
    best = None
    for form, items, acc in zip(r.get("form", []), r.get("items", []), r.get("acceptanceDateTime", [])):
        if form != "8-K" or "2.02" not in str(items): continue   # foreign issuers file 6-Ks with no item numbers: not checked
        try: at = dt.datetime.fromisoformat(acc[:19])          # Eastern time, see above
        except Exception: continue
        if abs((at.date() - dd).days) <= 4 and (best is None or abs((at.date() - dd).days) < abs((best.date() - dd).days)): best = at
    if best is None: continue
    hm = best.hour * 60 + best.minute
    tm = "bmo" if hm < 9 * 60 + 30 else "amc" if hm >= 16 * 60 else None
    if tm and tm != it.get("time"): it["time"] = tm; fixed += 1
    it["sec"] = 1
    if best.date() != dd: moves.append((x, it, best.date()))
for x, it, nd in moves:
    tgt = next((y for y, yd in days if yd == nd), None)
    if tgt is None: continue                                 # outside this week: leave it
    x["items"] = [i for i in x["items"] if i is not it]
    if not any(i["t"] == it["t"] for i in tgt["items"]): tgt["items"].append(it)
    it.pop("a", None)                                        # placed by SEC now: calendar_auto keeps it there
    fixed += 1
for x, _ in days: x["items"].sort(key=lambda i: i.get("time") != "bmo")
print("checked", checked, "fixed", fixed, "moved", len(moves), flush=True)
if fixed or todo:
    p.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
