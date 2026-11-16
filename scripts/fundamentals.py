"""Quarterly fundamentals from SEC EDGAR (US filers only) -> fund/<TICKER>.json

Runs weekly in GitHub Actions. For every stock on the site (themes.stocks + reports)
it looks up the CIK, downloads the XBRL "companyfacts" file and builds the last
20 quarters of: revenue, operating income, net income, gross profit, operating
expenses, diluted EPS, free cash flow, total assets, total liabilities.
Foreign filers (20-F / 40-F, no 10-Q) are skipped.
"""
import json, os, sys, time, datetime as dt
import urllib.request

import re as _re
UA = " ".join(_re.sub(r"[^\x20-\x7e]", " ", os.environ.get("SEC_UA") or "").split()) or "Wallstreeter sagirozio@users.noreply.github.com"
if "@" not in UA: print("warning: SEC_UA has no email after cleanup", flush=True)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "fund")
NQ = 20

def get(url, tries=3):
    import gzip
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "gzip, deflate"})
            with urllib.request.urlopen(req, timeout=30) as r:
                b = r.read()
                if r.headers.get("Content-Encoding") == "gzip" or b[:2] == b"\x1f\x8b": b = gzip.decompress(b)
                return json.loads(b)
        except urllib.error.HTTPError as e:
            print("http", e.code, url, flush=True)
            if e.code == 404: return None
            time.sleep(1.5 * (i + 1))
        except Exception as e:
            print("fail", type(e).__name__, str(e)[:120], url, flush=True)
            time.sleep(1.5 * (i + 1))
    return None

TAGS = {
    "rev": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "RevenueFromContractWithCustomerIncludingAssessedTax",
            "SalesRevenueNet", "RevenuesNetOfInterestExpense", "InterestAndDividendIncomeOperating"],
    "op": ["OperatingIncomeLoss"],
    "ni": ["NetIncomeLoss", "ProfitLoss", "NetIncomeLossAvailableToCommonStockholdersBasic"],
    "gp": ["GrossProfit"],
    "opex": ["OperatingExpenses", "CostsAndExpenses"],
    "eps": ["EarningsPerShareDiluted", "EarningsPerShareBasicAndDiluted", "EarningsPerShareBasic"],
    "cfo": ["NetCashProvidedByUsedInOperatingActivities", "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"],
    "assets": ["Assets"],
    "liab": ["Liabilities"],
}
INSTANT = {"assets", "liab"}

def d(s): return dt.date.fromisoformat(s)

def units(facts, tag):
    f = facts.get("us-gaap", {}).get(tag)
    if not f: return []
    u = f.get("units", {})
    return u.get("USD") or u.get("USD/shares") or []

def quarterly_flow(rows):
    """Return {end_date: value} for ~3-month periods, deriving from YTD/annual totals when needed."""
    by = {}
    for r in rows:
        if "start" not in r or r.get("form") not in ("10-Q", "10-K", "10-Q/A", "10-K/A"): continue
        k = (r["start"], r["end"])
        if k not in by or r.get("filed", "") > by[k][1]: by[k] = (r["val"], r.get("filed", ""))
    vals = {k: v[0] for k, v in by.items()}
    q = {}
    for (s, e), v in vals.items():
        if 75 <= (d(e) - d(s)).days <= 105: q[e] = v
    # derive missing quarters: cumulative(s, e) - cumulative(s, prev_end)
    for _ in range(2):
        for (s, e), v in vals.items():
            n = (d(e) - d(s)).days
            if n < 150 or e in q: continue
            prev = [(e2, v2) for (s2, e2), v2 in vals.items() if s2 == s and 0 < (d(e) - d(e2)).days <= 105 and (d(e) - d(e2)).days >= 75]
            if prev: q[e] = v - prev[0][1]; continue
            # annual minus three known quarters inside it
            if 340 <= n <= 380:
                inside = sorted(e2 for e2 in q if d(s) < d(e2) < d(e) and (d(e) - d(e2)).days >= 75)
                if len(inside) == 3: q[e] = v - sum(q[x] for x in inside)
    return q

def quarterly_instant(rows):
    q = {}
    for r in rows:
        if "start" in r or r.get("form") not in ("10-Q", "10-K", "10-Q/A", "10-K/A"): continue
        q[r["end"]] = r["val"]
    return q

def build(facts):
    series = {}
    for k, tags in TAGS.items():
        best = {}
        for tg in tags:
            rows = units(facts, tg)
            if not rows: continue
            q = quarterly_instant(rows) if k in INSTANT else quarterly_flow(rows)
            for e, v in q.items(): best.setdefault(e, v)   # earlier tags win, later fill gaps
        series[k] = best
    ends = sorted(set(series["rev"]) | set(series["ni"]) | set(series["eps"]))
    if not ends: return None
    # snap ends of all series to the revenue/NI calendar (within 10 days)
    def at(k, e):
        s = series[k]
        if e in s: return s[e]
        for e2, v in s.items():
            if abs((d(e2) - d(e)).days) <= 10: return v
        return None
    # de-duplicate ends that are within 10 days of each other
    uniq = []
    for e in ends:
        if uniq and (d(e) - d(uniq[-1])).days <= 10: uniq[-1] = e
        else: uniq.append(e)
    uniq = uniq[-NQ:]
    out = {"q": [], "rev": [], "op": [], "ni": [], "gp": [], "opex": [], "eps": [], "fcf": [], "assets": [], "liab": []}
    for e in uniq:
        out["q"].append(e)
        for k in ("rev", "op", "ni", "gp", "opex", "eps", "assets", "liab"):
            v = at(k, e); out[k].append(None if v is None else (round(v, 3) if k == "eps" else round(v)))
        cfo, cap = at("cfo", e), at("capex", e)
        out["fcf"].append(None if cfo is None else round(cfo - (cap or 0)))
    # if no opex tag but have gp and op: opex = gp - op
    for i in range(len(uniq)):
        if out["opex"][i] is None and out["gp"][i] is not None and out["op"][i] is not None:
            out["opex"][i] = out["gp"][i] - out["op"][i]
    return out

def main():
    data = json.load(open(os.path.join(ROOT, "data.json")))
    tick = set()
    for lst in (data.get("themes", {}).get("stocks") or {}).values():
        for s in lst: tick.add(s[0])
    for r in data.get("reports", []): tick.add(r["t"])
    only = sys.argv[1:]
    if only: tick = set(only)
    m = get("https://www.sec.gov/files/company_tickers.json")
    if not m: print("cannot load SEC ticker map"); sys.exit(1)
    cik = {v["ticker"].upper(): v["cik_str"] for v in m.values()}
    os.makedirs(OUT, exist_ok=True)
    ok = skip = 0; index = {}
    for i, t in enumerate(sorted(tick)):
        c = cik.get(t.upper()) or cik.get(t.upper().replace(".", "-")) or cik.get(t.upper().replace("-", "."))
        if not c: skip += 1; continue
        f = get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{int(c):010d}.json")
        time.sleep(0.12)
        if not f: skip += 1; continue
        try: res = build(f.get("facts", {}))
        except Exception as e: print("err", t, e); res = None
        if not res or len(res["q"]) < 4 or not any(v is not None for v in res["rev"][-4:] + res["ni"][-4:]):
            skip += 1; continue
        # foreign filers that file 20-F won't have recent 10-Q; require a quarter in the last ~200 days
        if (dt.date.today() - d(res["q"][-1])).days > 200: skip += 1; continue
        res["t"] = t; res["src"] = "SEC EDGAR"; res["asOf"] = dt.date.today().isoformat()
        json.dump(res, open(os.path.join(OUT, f"{t}.json"), "w"), separators=(",", ":"))
        index[t] = res["q"][-1]; ok += 1
        if i % 200 == 0: print(i, t, ok, skip, flush=True)
    json.dump(index, open(os.path.join(OUT, "_index.json"), "w"), separators=(",", ":"))
    print("done ok", ok, "skip", skip)

if __name__ == "__main__":
    main()
