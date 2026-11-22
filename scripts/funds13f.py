"""What well-known funds hold: their quarterly 13F reports (SEC EDGAR) -> funds13f.json (the "funds" tool on the research page).

A 13F report lists the US-listed shares an investment manager held on the last day of a quarter. It is filed up to
45 days after the quarter ends. For every fund on the list below the script reads the latest report and the one before it:
  submissions API (list of filings) -> the full text of each 13F-HR (and its amendments) -> the information table (XML)
  -> rows added up per security -> weight in the portfolio, and the change in the number of shares against the previous
  report (new / added / reduced / sold out / unchanged).
Tickers: a 13F names a security by its CUSIP, so the larger positions are looked up at OpenFIGI (free, no key needed;
OPENFIGI_KEY speeds it up). The lookups are cached in scripts/f13_map.json, keyed by a hash (CUSIPs are not stored).
Not in a 13F, so not here: short positions, cash, bonds, shares listed outside the US. Options are listed apart.
Facts only. Runs daily (funds13f.yml); the file changes only when a fund files a new report.
Usage: python scripts/funds13f.py [fund ids...]   (ids: only these funds are refreshed, the rest are kept)"""
import json, os, re, sys, time, gzip, hashlib, pathlib, statistics, urllib.request, urllib.error, datetime as dt
import xml.etree.ElementTree as ET

root = pathlib.Path(__file__).resolve().parent.parent
OUT, MAPF = root / "funds13f.json", root / "scripts" / "f13_map.json"
UA = " ".join(re.sub(r"[^\x20-\x7e]", " ", os.environ.get("SEC_UA") or "").split()) or "Wallstreeter bot@users.noreply.github.com"

# id, CIK (or the filer's own ticker: its CIK is then read from the SEC's ticker list), a word that must be in the SEC's
# name of the filer (a wrong CIK must never show another fund's holdings), display name, Hebrew name, the person the fund is known for
FUNDS = [
    ("brk", 1067983, "berkshire", "Berkshire Hathaway", "ברקשייר האת׳וויי", "וורן באפט (יו״ר) · גרג אייבל (מנכ״ל)"),
    ("psq", "PS", "pershing square", "Pershing Square", "פרשינג סקוור", "ביל אקמן"),              # files as Pershing Square Inc. (NYSE: PS) since 2026
    ("duq", 1536411, "duquesne", "Duquesne Family Office", "דוקיין", "סטנלי דרקנמילר"),
    ("app", 1656456, "appaloosa", "Appaloosa", "אפלוסה", "דיוויד טפר"),
    ("tp", 1040273, "third point", "Third Point", "ת׳רד פוינט", "דן לואב"),
    ("bau", 1061768, "baupost", "Baupost Group", "באופוסט", "סת׳ קלרמן"),
    ("gl", 1489933, "dme capital", "Greenlight Capital", "גרינלייט", "דיוויד איינהורן"),        # files as DME Capital Management
    ("tig", 1167483, "tiger global", "Tiger Global", "טייגר גלובל", "צ׳ייס קולמן"),
    ("coa", 1135730, "coatue", "Coatue", "קואטו", "פיליפ לאפונט"),
    ("sor", 1029160, "soros", "Soros Fund Management", "קרן סורוס", "ג׳ורג׳ סורוס (מייסד)"),
    ("ica", 921669, "icahn", "Icahn", "אייקן", "קרל אייקן"),
    ("lp", 1061165, "lone pine", "Lone Pine Capital", "לון פיין", "סטיבן מנדל (מייסד)"),
    ("vik", 1103804, "viking", "Viking Global", "ויקינג גלובל", "אנדראס הלבורסן"),
    ("ark", 1697748, "ark invest", "ARK Invest", "ארק אינווסט", "קת׳י ווד"),
    ("gat", 1166559, "gates", "Gates Foundation Trust", "קרן גייטס", "ביל גייטס"),
    ("him", 1709323, "himalaya", "Himalaya Capital", "הימלאיה קפיטל", "לי לו"),
    ("pab", 1549575, "dalal", "Dalal Street", "דלאל סטריט", "מוניש פבראי"),
    ("akr", 1112520, "akre", "Akre Capital", "אקרה קפיטל", "צ׳אק אקרה (מייסד)"),
    ("tci", 1647251, "tci", "TCI Fund Management", "TCI", "כריס הון"),
    ("alt", 1541617, "altimeter", "Altimeter Capital", "אלטימטר", "בראד גרסטנר"),
    ("d1", 1747057, "d1 capital", "D1 Capital", "D1 קפיטל", "דן סנדהיים"),
    ("bw", 1350694, "bridgewater", "Bridgewater Associates", "ברידג׳ווטר", "ריי דליו (מייסד)"),
    ("ell", 1791786, "elliott", "Elliott Management", "אליוט", "פול סינגר"),
    ("oak", 949509, "oaktree", "Oaktree Capital", "אוקטרי", "הווארד מרקס (מייסד שותף)"),
    ("fs", 1569205, "fundsmith", "Fundsmith", "פאנדסמית׳", "טרי סמית׳"),
    ("mkl", 1096343, "markel", "Markel Group", "מרקל", "טום גיינר"),
    ("pau", 1035674, "paulson", "Paulson & Co", "פולסון", "ג׳ון פולסון"),
    ("sci", 1649339, "scion", "Scion Asset Management", "סאיון", "מייקל ברי"),
]
TOP = 60          # positions kept per fund (largest first)
SIG = 0.25        # % of the portfolio: smaller positions are not counted in "bought / sold by the most funds"
MOVE = 5.0        # % change in the number of shares that counts as bought / sold in those lists

last = [0.0]
def get(url, raw=False):
    for i in range(4):
        w = 0.13 - (time.time() - last[0])
        if w > 0: time.sleep(w)
        last[0] = time.time()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "gzip"})
            with urllib.request.urlopen(req, timeout=40) as r:
                b = r.read()
                if b[:2] == b"\x1f\x8b": b = gzip.decompress(b)
                return b.decode("utf-8", "replace") if raw else json.loads(b)
        except urllib.error.HTTPError as e:
            if e.code in (403, 404): print(f"  http {e.code}: {url}"); return None
            time.sleep(3 * (i + 1))
        except Exception as e:
            time.sleep(3 * (i + 1))
    print(f"  failed: {url}"); return None

TICKERS = {}
def cik_of(x):
    """a CIK, or the ticker of a listed filer -> CIK"""
    if isinstance(x, int): return x
    if not TICKERS:
        for v in (get("https://www.sec.gov/files/company_tickers.json") or {}).values(): TICKERS.setdefault(str(v.get("ticker", "")).upper(), int(v.get("cik_str") or 0))
    return TICKERS.get(x.upper()) or 0

# ---------- reading a filing
loc = lambda e: e.tag.rsplit("}", 1)[-1]
def first(e, name):
    for c in e.iter():
        if loc(c) == name: return (c.text or "").strip()
    return ""
def num(s):
    try: return float(str(s).replace(",", "").strip() or 0)
    except ValueError: return 0.0

def parse_table(xml):
    """information table -> [{c: cusip, n: issuer, k: class, v: value, sh: shares, pc: '' | 'Put' | 'Call'}], bonds left out"""
    rows = []
    for it in ET.fromstring(xml.encode("utf-8")).iter():
        if loc(it) != "infoTable": continue
        g = {loc(c): c for c in it}
        tx = lambda k: ((g[k].text or "").strip() if k in g else "")
        sp = g.get("shrsOrPrnAmt"); sh, typ = 0.0, ""
        if sp is not None:
            for c in sp:
                if loc(c) == "sshPrnamt": sh = num(c.text)
                elif loc(c) == "sshPrnamtType": typ = (c.text or "").strip().upper()
        if typ == "PRN": continue                                   # a principal amount: bonds and notes
        pc = tx("putCall").capitalize()
        rows.append({"c": tx("cusip").upper().replace(" ", ""), "n": tx("nameOfIssuer"), "k": tx("titleOfClass"), "v": num(tx("value")), "sh": sh, "pc": pc if pc in ("Put", "Call") else ""})
    return rows

def read_filing(cik, acc):
    """-> (rows, {amend: '' | 'RESTATEMENT' | 'NEW HOLDINGS', total: the filing's own total}) or None"""
    txt = get(f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/{acc}.txt", raw=True)
    if not txt: return None
    rows, meta = None, {"amend": "", "total": 0.0}
    for x in re.findall(r"<XML>\s*(.*?)\s*</XML>", txt, re.S):
        try:
            if re.search(r"<(\w+:)?informationTable[\s>]", x[:4000]): rows = parse_table(x)
            elif re.search(r"<(\w+:)?edgarSubmission[\s>]", x[:4000]):
                e = ET.fromstring(x.encode("utf-8"))
                if first(e, "isAmendment").lower() == "true": meta["amend"] = first(e, "amendmentType").upper() or "RESTATEMENT"
                meta["total"] = num(first(e, "tableValueTotal"))
        except ET.ParseError as err: print(f"  xml error in {acc}: {err}")
    if rows is None: return None
    # reports before 2023 gave values in thousands of dollars, and a few filers still do: a median "price" under $1 shows it
    px = [r["v"] / r["sh"] for r in rows if r["sh"] > 0 and not r["pc"] and r["v"] > 0]
    if px and statistics.median(px) < 1.0:
        for r in rows: r["v"] *= 1000
        meta["total"] *= 1000
    tot = sum(r["v"] for r in rows)
    if meta["total"] and not meta["amend"] and abs(tot / meta["total"] - 1) > 0.02: print(f"  note {acc}: rows add up to {tot:,.0f}, the filing says {meta['total']:,.0f} (bonds are left out)")
    return rows, meta

def period_rows(cik, fl):
    """all the filings of one quarter (the report and its amendments), oldest first -> one list of rows"""
    rows = None
    for f in sorted(fl, key=lambda f: (f["filed"], f["acc"])):
        r = read_filing(cik, f["acc"])
        if not r: continue
        if rows is not None and r[1]["amend"].startswith("NEW"): rows = rows + r[0]      # an amendment that adds holdings
        else: rows = r[0]                                                                  # the report, or a full restatement
    return rows

def book(rows):
    """rows -> shares per security {cusip: {...}}, options [{...}]"""
    pos, opt = {}, {}
    for r in rows:
        if not r["c"]: continue
        d = (opt if r["pc"] else pos).setdefault((r["c"], r["pc"]) if r["pc"] else r["c"], {"c": r["c"], "n": r["n"], "k": r["k"], "v": 0.0, "sh": 0.0, "pc": r["pc"]})
        d["v"] += r["v"]; d["sh"] += r["sh"]
    return {c: p for c, p in pos.items() if p["v"] > 0 or p["sh"] > 0}, sorted(opt.values(), key=lambda o: -o["v"])

# ---------- CUSIP -> ticker (OpenFIGI), cached under a hash of the CUSIP
hk = lambda c: hashlib.sha1(c.encode()).hexdigest()[:16]
CACHE = json.loads(MAPF.read_text(encoding="utf-8")) if MAPF.exists() else {}
TODAY = dt.date.today().isoformat()
KEEP_UP = {"ETF", "ETFS", "SPDR", "ADR", "USA", "US", "NV", "SA", "SE", "AG", "PLC", "LP", "LLC", "REIT", "II", "III", "IV", "AI", "IBM", "HP", "AT&T", "S&P", "KKR", "CVS", "UPS", "TJX", "HCA", "GE", "BP", "CRH", "RH", "NRG", "MSCI", "QQQ", "ASML", "SAP", "UBS", "ICICI", "HDFC", "NU", "ON"}
def nice(name):
    """APPLE INC -> Apple Inc; share-class and ADR endings are dropped"""
    x = re.sub(r"\s+", " ", (name or "").upper()).strip()
    x = re.sub(r"/THE$", "", x)
    x = re.sub(r"[- ](CL(ASS)? ?[A-Z]( SHARES| SHS)?|SP(ONS)? ?ADR|ADR|REG|W/I|NEW)$", "", x).strip(" -")
    return " ".join(w if (w in KEEP_UP or (len(w) <= 4 and "&" in w)) else "-".join(q.capitalize() for q in w.split("-")) for w in x.split(" "))[:48]
US_EX = {"US", "UN", "UW", "UQ", "UR", "UA", "UP", "UF", "UV"}
def figi(jobs, key):
    for a in range(5):
        try:
            req = urllib.request.Request("https://api.openfigi.com/v3/mapping", data=json.dumps(jobs).encode(), headers={"Content-Type": "application/json", **({"X-OPENFIGI-APIKEY": key} if key else {})})
            with urllib.request.urlopen(req, timeout=40) as r: res = json.loads(r.read())
            if isinstance(res, list) and len(res) == len(jobs): return res
        except urllib.error.HTTPError as e:
            print(f"  OpenFIGI http {e.code}"); time.sleep(30 if e.code == 429 else 5 * (a + 1))
        except Exception as e:
            print(f"  OpenFIGI error {e}"); time.sleep(5 * (a + 1))
    return None
def lookup(cusips):
    """fills CACHE for the CUSIPs that are not in it. Two passes: US listings only, then (for the ones not found) every listing, of which a US one is taken"""
    old = (dt.date.today() - dt.timedelta(days=30)).isoformat()
    need = [c for c in dict.fromkeys(cusips) if hk(c) not in CACHE or (CACHE[hk(c)][0] is None and CACHE[hk(c)][-1] < old)]
    key = os.environ.get("OPENFIGI_KEY") or ""; B = 100 if key else 10
    if need: print(f"OpenFIGI: {len(need)} securities to look up")
    typ = lambda c: "ID_CINS" if c[:1].isalpha() else "ID_CUSIP"          # a foreign company listed in the US has a CINS: it starts with a letter
    good = ("Common Stock", "Depositary Receipt", "REIT", "ETP", "Mutual Fund", "Partnership Shares", "MLP", "Unit")
    for us in (True, False):
        bad = 0
        for i in range(0, len(need), B):
            if bad >= 3: print("  OpenFIGI does not answer: the rest is left for the next run"); break
            part = need[i:i + B]
            res = figi([{"idType": typ(c), "idValue": c, **({"exchCode": "US"} if us else {})} for c in part], key)
            if res is None: bad += 1; continue
            for c, r in zip(part, res):
                d = [x for x in (r.get("data") or []) if x.get("ticker") and (us or x.get("exchCode") in US_EX)]
                p = ([x for x in d if (x.get("securityType2") or "") in good] or d or [None])[0]
                CACHE[hk(c)] = [p["ticker"].replace("/", "-").replace(" ", "-").upper(), nice(p.get("name")), TODAY] if p else [None, TODAY]
            time.sleep(0.3 if key else 2.6)                                # without a key: 25 requests a minute
        need = [c for c in need if (CACHE.get(hk(c)) or [None])[0] is None]
        if not need: break
        if us: print(f"  {len(need)} not found among the US listings, second pass")

# ---------- one fund
def quarter(d): return f"Q{(int(d[5:7]) - 1) // 3 + 1} {d[:4]}"
def change(cur, prv):
    """-> (what happened, % change in the number of shares)"""
    if not prv or prv["sh"] <= 0: return "new", None
    if cur["sh"] <= 0: return "hold", 0.0
    r, vr = cur["sh"] / prv["sh"], cur["v"] / max(prv["v"], 1.0)
    for k in (2, 3, 4, 5, 10, 15, 20, 25, 50):     # a share split between the two reports is not a purchase (a reverse split is not a sale)
        if abs(r / k - 1) < 0.002 and vr < k * 0.7: r = 1.0
        if abs(r * k - 1) < 0.002 and vr > 1.4 / k: r = 1.0
    c = round((r - 1) * 100, 1)
    return ("hold", 0.0) if abs(c) < 0.5 else (("add" if c > 0 else "cut"), c)

def fund(fid, cik, word, name, he, who):
    cik = cik_of(cik)
    if not cik: print(f"{fid}: no CIK found"); return None
    sub = get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json")
    if not sub: print(f"{fid}: no answer from the SEC"); return None
    if word not in (sub.get("name") or "").lower(): print(f"{fid}: CIK {cik} belongs to \"{sub.get('name')}\", expected \"{word}\". Skipped."); return False
    r = sub["filings"]["recent"]
    fl = [{"form": f, "acc": r["accessionNumber"][i], "filed": r["filingDate"][i], "period": r["reportDate"][i]} for i, f in enumerate(r["form"]) if f in ("13F-HR", "13F-HR/A") and r["reportDate"][i]]
    periods = sorted({f["period"] for f in fl}, reverse=True)
    if not periods: print(f"{fid}: no 13F-HR among the recent filings"); return False
    p1, p0 = periods[0], (periods[1] if len(periods) > 1 else None)
    rows1 = period_rows(cik, [f for f in fl if f["period"] == p1])
    if rows1 is None: print(f"{fid}: could not read the report for {p1}"); return None
    rows0 = period_rows(cik, [f for f in fl if f["period"] == p0]) if p0 else None
    if p0 and rows0 is None: print(f"{fid}: could not read the report for {p0}"); return None
    cur, opt = book(rows1); prv, _ = book(rows0 or [])
    tot, ptot = sum(p["v"] for p in cur.values()), sum(p["v"] for p in prv.values())
    if tot <= 0: print(f"{fid}: the report for {p1} has no shares"); return False
    top = sorted(cur.values(), key=lambda p: -p["v"])
    ptop = sorted(prv.values(), key=lambda p: -p["v"])
    f1 = max((f for f in fl if f["period"] == p1 and f["form"] == "13F-HR"), key=lambda f: f["filed"], default=max((f for f in fl if f["period"] == p1), key=lambda f: f["filed"]))
    return {"id": fid, "cik": cik, "name": name, "he": he, "who": who, "period": p1, "prev": p0, "filed": f1["filed"], "acc": f1["acc"],
            "_cur": cur, "_prv": prv, "_top": top, "_ptop": ptop, "_opt": opt, "tot": tot, "ptot": ptot}

def finish(F):
    """tickers, weights and changes for one fund (after the look-up)"""
    cur, prv, tot, ptot = F.pop("_cur"), F.pop("_prv"), F["tot"], F["ptot"]
    top, ptop, opt = F.pop("_top"), F.pop("_ptop"), F.pop("_opt")
    tk = lambda p: (CACHE.get(hk(p["c"])) or [None])[0]
    nm = lambda p: nice((CACHE.get(hk(p["c"])) or [None, None])[1] if tk(p) else p["n"]) or nice(p["n"])
    # a security whose CUSIP changed between the two reports (a merger, a new share class) is the same holding: match by ticker too
    prv_t = {}
    for p in prv.values():
        t = tk(p)
        if t and p["c"] not in cur: prv_t.setdefault(t, p)
    cnt = {"new": 0, "add": 0, "cut": 0, "hold": 0, "out": 0}; rows = []; seen = set()
    for p in top:
        q = prv.get(p["c"]) or prv_t.get(tk(p))
        if q: seen.add(q["c"])
        a, c = change(p, q) if F["prev"] else ("hold", None)
        cnt[a] += 1
        rows.append({"t": tk(p), "n": nm(p), "w": round(p["v"] / tot * 100, 2), "v": round(p["v"]), "sh": round(p["sh"]), "a": a, "c": c, "pw": round(q["v"] / ptot * 100, 2) if q and ptot else None})
    out = [{"t": tk(p), "n": nm(p), "pw": round(p["v"] / ptot * 100, 2), "pv": round(p["v"])} for p in ptop if p["c"] not in cur and p["c"] not in seen] if F["prev"] else []
    cnt["out"] = len(out)
    for p in top[:TOP]:                                                 # a large position without a ticker: shown in the log (the CUSIP is in the public filing)
        if not tk(p) and p["v"] / tot >= 0.01: print(f"  {F['id']}: no ticker for {p['c']} {p['n']} ({p['k']}), {p['v'] / tot * 100:.1f}%")
    F.update({"val": round(tot), "pval": round(ptot) if F["prev"] else None, "n": len(cur), "t10": round(sum(r["w"] for r in rows[:10]), 1), "cnt": cnt,
              "url": f"https://www.sec.gov/Archives/edgar/data/{F['cik']}/{F['acc'].replace('-', '')}/",
              "top": rows[:TOP], "out": out[:30],
              "opt": [{"t": tk(o), "n": nm(o), "pc": o["pc"], "v": round(o["v"])} for o in opt[:8]], "_all": rows, "_out": out})
    for k in ("tot", "ptot", "acc"): F.pop(k, None)
    return F

def main():
    only = set(sys.argv[1:])
    old = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    oldf = {f["id"]: f for f in old.get("funds", [])}
    got, kept = [], []
    for row in FUNDS:
        fid = row[0]
        if only and fid not in only:
            if fid in oldf: kept.append(oldf[fid])
            continue
        try: F = fund(*row)
        except Exception as e: print(f"{fid}: error {type(e).__name__}: {e}"); F = None
        if F: got.append(F); print(f"{fid}: {F['period']} (filed {F['filed']}), {len(F['_cur'])} shares, ${F['tot'] / 1e9:,.1f}B, previous {F['prev']}")
        elif F is None and fid in oldf: kept.append(oldf[fid]); print(f"{fid}: kept the previous data")
    if not got and not kept: raise SystemExit("no fund could be read")
    # tickers for the positions that are shown or counted: the largest ones now and before
    want = []
    for F in got:
        want += [p["c"] for i, p in enumerate(F["_top"]) if i < TOP or p["v"] / F["tot"] * 100 >= SIG]
        want += [p["c"] for i, p in enumerate(F["_ptop"]) if i < TOP // 2 or (F["ptot"] and p["v"] / F["ptot"] * 100 >= SIG)]
        want += [o["c"] for o in F["_opt"][:8]]
    lookup(want)
    MAPF.write_text(json.dumps(CACHE, ensure_ascii=False, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    funds = [finish(F) for F in got]
    # the quarter of the overview: the newest one that at least a third of the funds have reported
    per = {}
    for f in funds + kept: per[f["period"]] = per.get(f["period"], 0) + 1
    cut = max(3, (len(funds) + len(kept)) // 3)
    gp = max([p for p, n in per.items() if n >= cut] or per)
    gprev = f"{int(gp[:4]) - (gp[5:7] == '03')}-{({'03': '12-31', '06': '03-31', '09': '06-30', '12': '09-30'}).get(gp[5:7], gp[5:])}"
    funds = [f for f in funds if f["period"] >= gprev]                 # a fund that stopped reporting drops out
    kept = [f for f in kept if f["period"] >= gprev]
    # overview over the funds that reported the quarter (the kept ones carry no full list, so they add nothing here)
    buy, sell, held = {}, {}, {}
    key = lambda r: r["t"] or r["n"]
    for f in funds:
        if f["period"] != gp: continue
        for r in f["_all"]:
            if r["w"] >= SIG:
                held.setdefault(key(r), {"t": r["t"], "n": r["n"], "f": []})["f"].append([f["id"], r["w"]])
                if r["a"] == "new" or (r["a"] == "add" and (r["c"] or 0) >= MOVE):
                    buy.setdefault(key(r), {"t": r["t"], "n": r["n"], "new": [], "add": []})[r["a"]].append(f["id"])
            if r["a"] == "cut" and (r["c"] or 0) <= -MOVE and (r["pw"] or 0) >= SIG:
                sell.setdefault(key(r), {"t": r["t"], "n": r["n"], "out": [], "cut": []})["cut"].append(f["id"])
        for r in f["_out"]:
            if r["pw"] >= SIG: sell.setdefault(key(r), {"t": r["t"], "n": r["n"], "out": [], "cut": []})["out"].append(f["id"])
    for f in funds: f.pop("_all", None); f.pop("_out", None)
    agg = None
    if old.get("agg") and old.get("period") == gp and any(f["period"] == gp for f in kept): agg = old["agg"]     # a fund could not be read today: a partial count would mislead
    elif any(f["period"] == gp for f in funds):
        agg = {"n": sum(1 for f in funds if f["period"] == gp),
               "buy": sorted(buy.values(), key=lambda x: (-(len(x["new"]) + len(x["add"])), -len(x["new"]), x["n"]))[:20],
               "sell": sorted(sell.values(), key=lambda x: (-(len(x["out"]) + len(x["cut"])), -len(x["out"]), x["n"]))[:20],
               "held": sorted(held.values(), key=lambda x: (-len(x["f"]), -sum(w for _, w in x["f"])))[:20]}
        for h in agg["held"]: h["f"].sort(key=lambda z: -z[1])
    allf = sorted(funds + kept, key=lambda f: -f["val"])
    res = {"period": gp, "prev": gprev, "sig": SIG, "move": MOVE, "funds": allf, "agg": agg}
    same = {k: v for k, v in old.items() if k != "asOf"} == res
    res = {"asOf": old.get("asOf", TODAY) if same else TODAY, **res}
    OUT.write_text(json.dumps(res, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"funds13f.json: {len(allf)} funds, quarter {quarter(gp)}, {'no change' if same else 'updated'}, {OUT.stat().st_size // 1024} KB")

if __name__ == "__main__": main()
