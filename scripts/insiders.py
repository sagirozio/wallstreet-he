"""Insider trades (SEC Form 4) for the stocks on the site -> data.json["insiders"] (last 30 days).
Source: EDGAR daily form index (all filings of a day) -> Form 4 filings whose issuer is one of our companies ->
open-market buys (code P) and sells (code S) by directors / officers / 10% owners.
Kept: buys >= $250k, sells >= $1M. 10b5-1 planned trades are marked. Runs nightly (insiders.yml)."""
import json, os, re, sys, time, gzip, pathlib, urllib.request, urllib.error, datetime as dt
import xml.etree.ElementTree as ET
root = pathlib.Path(__file__).resolve().parent.parent
UA = " ".join(re.sub(r"[^\x20-\x7e]", " ", os.environ.get("SEC_UA") or "").split()) or "Wallstreeter bot@users.noreply.github.com"
last = [0.0]
def get(url, raw=False):
    for i in range(3):
        w = 0.12 - (time.time() - last[0])
        if w > 0: time.sleep(w)
        last[0] = time.time()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "gzip"})
            with urllib.request.urlopen(req, timeout=30) as r:
                b = r.read()
                if b[:2] == b"\x1f\x8b": b = gzip.decompress(b)
                return b.decode("utf-8", "replace") if raw else json.loads(b)
        except urllib.error.HTTPError as e:
            if e.code in (403, 404): return None
            time.sleep(2 * (i + 1))
        except Exception: time.sleep(2 * (i + 1))
    return None
p = root / "data.json"; d = json.loads(p.read_text(encoding="utf-8"))
U = {s[0]: (s[1], s[2]) for lst in d.get("themes", {}).get("stocks", {}).values() for s in lst}
m = get("https://www.sec.gov/files/company_tickers.json")
if not m: raise SystemExit("no SEC ticker map")
cik2t = {}
for v in m.values():
    t = v["ticker"].upper().replace(".", "-")
    if t in U and v["cik_str"] not in cik2t: cik2t[v["cik_str"]] = t
print("our companies with a CIK", len(cik2t), flush=True)
old = d.get("insiders") or {}
rows = old.get("rows", []); seen = {r["id"] for r in rows}; done = set(old.get("days", []))
today = dt.date.today()
days = [today - dt.timedelta(days=k) for k in range(1, int(sys.argv[1]) + 1 if len(sys.argv) > 1 else 6)]
added = 0
for day in days:
    if day.weekday() >= 5 or day.isoformat() in done: continue
    qtr = (day.month - 1) // 3 + 1
    idx = get(f"https://www.sec.gov/Archives/edgar/daily-index/{day.year}/QTR{qtr}/form.{day:%Y%m%d}.idx", raw=True)
    if not idx: print(day, "no index (yet)"); continue
    files = set()
    for line in idx.splitlines():
        if not line.startswith("4 "): continue
        parts = re.split(r"\s{2,}", line.strip())
        if len(parts) < 5: continue
        try: c = int(parts[-3])
        except ValueError: continue
        if c in cik2t: files.add((cik2t[c], parts[-1]))
    print(day, "form 4 filings for our companies:", len(files), flush=True)
    for t, path in sorted(files):
        txt = get("https://www.sec.gov/Archives/" + path, raw=True)
        if not txt: continue
        mx = re.search(r"<ownershipDocument>.*?</ownershipDocument>", txt, re.S)
        if not mx: continue
        try: x = ET.fromstring(mx.group(0))
        except ET.ParseError: continue
        g = lambda e, k: (e.findtext(k) or "").strip()
        who = g(x, "reportingOwner/reportingOwnerId/rptOwnerName")
        rel = x.find("reportingOwner/reportingOwnerRelationship")
        role = ""
        if rel is not None:
            if g(rel, "officerTitle"): role = g(rel, "officerTitle")
            elif g(rel, "isDirector") in ("1", "true"): role = "Director"
            elif g(rel, "isTenPercentOwner") in ("1", "true"): role = "10% owner"
        plan = g(x, "aff10b5One") in ("1", "true") or "10b5-1" in txt[:200000]
        acc = path.rsplit("/", 1)[-1].replace(".txt", "")
        agg = {}
        for tr in x.findall("nonDerivativeTable/nonDerivativeTransaction"):
            code = g(tr, "transactionCoding/transactionCode")
            if code not in ("P", "S"): continue
            try:
                sh = float(g(tr, "transactionAmounts/transactionShares/value") or 0)
                px = float(g(tr, "transactionAmounts/transactionPricePerShare/value") or 0)
            except ValueError: continue
            a = agg.setdefault(code, [0.0, 0.0, g(tr, "transactionDate/value")[:10]])
            a[0] += sh; a[1] += sh * px
        for code, (sh, val, tdate) in agg.items():
            if (code == "P" and val < 250_000) or (code == "S" and val < 1_000_000): continue
            rid = f"{acc}-{code}"
            if rid in seen: continue
            cik_num = path.split("/")[2]
            rows.append({"id": rid, "t": t, "co": U[t][0], "who": who.title(), "role": role, "type": code,
                         "sh": int(sh), "px": round(val / sh, 2) if sh else None, "val": int(val), "date": tdate or day.isoformat(),
                         "filed": day.isoformat(), "plan": bool(plan),
                         "url": f"https://www.sec.gov/Archives/edgar/data/{cik_num}/{acc.replace('-', '')}/{acc}-index.htm"})
            seen.add(rid); added += 1
    done.add(day.isoformat())
cut = (today - dt.timedelta(days=30)).isoformat()
rows = sorted([r for r in rows if r["filed"] >= cut], key=lambda r: (r["filed"], r["val"]), reverse=True)
d["insiders"] = {"asOf": today.isoformat(), "rows": rows, "days": sorted(x for x in done if x >= cut)}
p.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
print("insiders added", added, "total", len(rows), "buys", sum(r["type"] == "P" for r in rows))
