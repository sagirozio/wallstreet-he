"""EPS vs estimate for the last quarters of every stock, from Finnhub (free tier: 4 quarters) -> earnhist.json
{T: [[period, fiscalYear, fiscalQuarter, actual, estimate], ...]} newest first. Old quarters are kept (merged by period, up to 12),
so the history grows over time. build.py joins it with fund/<T>.json (revenue, year-over-year) into s/<T>.json ("eh").
Usage: earnhist.py [minutes] [--recent N]   (--recent: only stocks with a report card in the last N days)"""
import json, os, sys, time, re, pathlib, urllib.request, urllib.parse, datetime as dt
KEY = os.environ.get("FINNHUB_KEY", "").strip()
if not KEY: raise SystemExit("FINNHUB_KEY missing")
root = pathlib.Path(__file__).resolve().parent.parent
d = json.loads((root / "data.json").read_text(encoding="utf-8"))
def cap(s):
    m = re.fullmatch(r"([\d.]+)([TBM])", str(s or "")); return float(m[1]) * {"T": 1e12, "B": 1e9, "M": 1e6}[m[2]] if m else 0
U = {s[0]: cap(s[2]) for l in d["themes"]["stocks"].values() for s in l}
out_p = root / "earnhist.json"
try: out = json.loads(out_p.read_text(encoding="utf-8"))
except Exception: out = {}
H = out.get("h", {}); last = [0.0]
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
args = sys.argv[1:]; recent = None
if "--recent" in args:
    i = args.index("--recent"); recent = int(args[i + 1]); del args[i:i + 2]
budget = int(args[0]) * 60 if args and args[0].isdigit() else 50 * 60
todo = sorted(U, key=lambda t: -U[t])
if recent is not None:
    since = (dt.date.today() - dt.timedelta(days=recent)).isoformat()
    todo = [t for t in todo if any(r.get("t") == t and str(r.get("date", "")) >= since for r in d.get("reports", []))]
t0 = time.time(); n = 0
for t in todo:
    if time.time() - t0 > budget: break
    j = get("stock/earnings", symbol=t.replace("-", "."))
    if not isinstance(j, list) or not j: continue
    rows = {r[0]: r for r in H.get(t, [])}
    for x in j:
        p, a = str(x.get("period") or "")[:10], x.get("actual")
        if not re.fullmatch(r"\d{4}-\d\d-\d\d", p) or a is None: continue
        e = x.get("estimate")
        rows[p] = [p, x.get("year"), x.get("quarter"), round(float(a), 2), None if e is None else round(float(e), 2)]
    if rows: H[t] = sorted(rows.values(), key=lambda r: r[0], reverse=True)[:12]; n += 1
    if n % 200 == 0: print("earnhist", n, flush=True)
out = {"asOf": dt.date.today().isoformat(), "h": {t: v for t, v in H.items() if t in U}}
out_p.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
print("earnhist: stocks", len(out["h"]), "updated", n, "of", len(todo))
