"""Raw English headlines per stock from Finnhub -> news_src.json (research material for the content runs; not shown on the site).
Order: today's 10%+ movers, this week's reporters, then by market cap. Stops after LIMIT_MIN minutes (free tier: 60 calls/min).
{"asOf": "...", "from": "YYYY-MM-DD", "n": <stocks checked>, "items": {T: [{"h","s","src","url","dt"}]}}"""
import json, os, pathlib, re, time, urllib.request, urllib.parse, datetime as dt
KEY = os.environ.get("FINNHUB_KEY", "").strip()
if not KEY: raise SystemExit("FINNHUB_KEY missing")
LIMIT_MIN = float(os.environ.get("LIMIT_MIN", "36"))
root = pathlib.Path(__file__).resolve().parent.parent
d = json.loads((root / "data.json").read_text(encoding="utf-8"))
U = {s[0]: s[2] for l in d["themes"]["stocks"].values() for s in l}
def capn(c):
    m = re.match(r"([\d.]+)([TBM])", c or ""); return float(m[1]) * {"T": 1e12, "B": 1e9, "M": 1e6}[m[2]] if m else 0
first = [r["t"] for r in (d.get("movers") or {}).get("rows", [])]
first += [i["t"] for day in (d.get("calendar") or {}).get("days", []) for i in day.get("items", [])]
order = list(dict.fromkeys([t for t in first if t in U] + sorted(U, key=lambda t: -capn(U[t]))))
today = dt.date.today(); frm = (today - dt.timedelta(days=2)).isoformat()
items, start, n = {}, time.time(), 0
for t in order:
    if time.time() - start > LIMIT_MIN * 60: break
    t0 = time.time()
    try:
        url = "https://finnhub.io/api/v1/company-news?" + urllib.parse.urlencode({"symbol": t.replace("-", "."), "from": frm, "to": today.isoformat(), "token": KEY})
        with urllib.request.urlopen(url, timeout=20) as r: rows = json.loads(r.read().decode())
        n += 1
        out = []
        for x in sorted(rows or [], key=lambda x: -(x.get("datetime") or 0))[:5]:
            out.append({"h": x.get("headline", ""), "s": (x.get("summary") or "")[:300], "src": x.get("source", ""), "url": x.get("url", ""),
                        "dt": dt.datetime.utcfromtimestamp(x.get("datetime") or 0).strftime("%Y-%m-%d %H:%M")})
        if out: items[t] = out
    except Exception as e:
        if "429" in str(e): time.sleep(30)
    time.sleep(max(0, 1.05 - (time.time() - t0)))
now = dt.datetime.now(dt.timezone(dt.timedelta(hours=2)))
(root / "news_src.json").write_text(json.dumps({"asOf": now.strftime("%d.%m.%Y · %H:%M"), "from": frm, "n": n, "items": items}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
print("checked", n, "with news", len(items))
