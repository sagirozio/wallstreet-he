"""Basic earnings cards straight from Yahoo Finance, for companies that have no card yet.
Fills: EPS actual vs estimate (Yahoo), EPS YoY, revenue (quarterly income statement) + YoY,
report date and the stock's reaction on the first trading day after the report.
Revenue estimate and guidance are not available from Yahoo for past quarters -> left empty;
the scheduled content runs can enrich these cards later (they carry "auto": true).

usage: python scripts/autoreports.py gainers20        # stocks up 20%+ in the last month, no card yet
       python scripts/autoreports.py NVDA AAPL ...     # specific tickers
       python scripts/autoreports.py big 100           # the 100 largest without a card
"""
import json, pathlib, sys, re, datetime as dt
import pandas as pd, yfinance as yf

root = pathlib.Path(__file__).resolve().parent.parent
p = root / "data.json"; data = json.loads(p.read_text(encoding="utf-8"))
SEC_HE = {"Technology": "טכנולוגיה", "Healthcare": "בריאות", "Financial Services": "פיננסים", "Consumer Cyclical": "צריכה מחזורית",
          "Consumer Defensive": "צריכה בסיסית", "Industrials": "תעשייה", "Energy": "אנרגיה", "Basic Materials": "חומרי גלם",
          "Real Estate": "נדל״ן", "Utilities": "תשתיות", "Communication Services": "תקשורת"}
T = data["themes"]; isec = T.get("indSector", {})
U = {}
for ind, lst in T["stocks"].items():
    for s in lst: U[s[0]] = {"co": s[1], "cap": s[2], "r": s[3] if isinstance(s[3], dict) else {}, "sec": SEC_HE.get(isec.get(ind, ""), "")}
have = {r["t"] for r in data["reports"]}
def capn(c):
    m = re.match(r"([\d.]+)([TBM])", c or ""); return float(m[1]) * {"T": 1e12, "B": 1e9, "M": 1e6}[m[2]] if m else 0

a = sys.argv[1:]
if a and a[0] == "gainers20":
    todo = sorted([t for t, x in U.items() if (x["r"].get("m") or 0) >= 20 and t not in have], key=lambda t: -U[t]["r"]["m"])
elif a and a[0] == "big":
    n = int(a[1]) if len(a) > 1 else 100
    todo = sorted([t for t in U if t not in have], key=lambda t: -capn(U[t]["cap"]))[:n]
elif a and a[0] == "recent":   # nightly: only companies whose report date (Yahoo) falls in the last 10 days
    import datetime as _d
    ed = data.get("earnDates") or {}; lo = (_d.date.today() - _d.timedelta(days=10)).isoformat(); hi = _d.date.today().isoformat()
    have_id = {r["id"] for r in data["reports"]}
    todo = [t for t in U if lo <= (ed.get(t) or {}).get("d", "") <= hi]
    have = {t for t in have if any(i.startswith(t + "-") and i >= f"{t}-{lo[:7]}" for i in have_id)}
    todo = [t for t in todo if t not in have]
else:
    todo = [t for t in a if t not in have]
todo = [t for t in todo if t != "GOOG" or "GOOGL" not in have]
print("todo", len(todo), flush=True)

def num(v):
    try:
        v = float(v); return None if pd.isna(v) else v
    except Exception: return None

today = pd.Timestamp.now(tz="America/New_York")
added = 0
for t in todo:
    try:
        tk = yf.Ticker(t)
        ed = tk.get_earnings_dates(limit=12)
        if ed is None or ed.empty: print(t, "no earnings dates"); continue
        ed = ed[ed.index <= today]
        ed = ed[ed["Reported EPS"].notna()] if "Reported EPS" in ed else ed.iloc[0:0]
        if ed.empty: print(t, "no reported EPS"); continue
        when = ed.index[0]; row = ed.iloc[0]
        if (today - when).days > 75: print(t, "last report too old", when.date()); continue
        eps_a, eps_e = num(row.get("Reported EPS")), num(row.get("EPS Estimate"))
        eps_y = None   # same quarter a year earlier = ~4 reports back
        old = ed[(ed.index <= when - pd.Timedelta(days=330)) & (ed.index >= when - pd.Timedelta(days=400))]
        if len(old):
            e0 = num(old.iloc[0]["Reported EPS"])
            if e0 is not None and eps_a is not None and e0 >= 0.01:   # a % change from a loss base means nothing
                eps_y = round((eps_a - e0) / e0 * 100)
        rev = rev_y = None; qlabel = ""
        qi = tk.quarterly_income_stmt
        if qi is not None and not qi.empty and "Total Revenue" in qi.index:
            rr = qi.loc["Total Revenue"].dropna()
            rr = rr[rr.index <= when.tz_localize(None)]
            if len(rr):
                pe = rr.index[0]
                if (when.tz_localize(None) - pe).days <= 120:
                    rev = rr.iloc[0] / 1e9 if rr.iloc[0] else None
                    qlabel = f"Q{(pe.month - 1) // 3 + 1} {pe.year}"
                    prev = rr[(rr.index <= pe - pd.Timedelta(days=330)) & (rr.index >= pe - pd.Timedelta(days=400))]
                    if rev and len(prev) and prev.iloc[0]: rev_y = round((rr.iloc[0] / prev.iloc[0] - 1) * 100, 1)
        try:
            if (tk.info or {}).get("financialCurrency", "USD") != "USD": rev = None   # amounts not in dollars
        except Exception: pass
        if not qlabel:
            pe = when - pd.Timedelta(days=50); qlabel = f"Q{(pe.month - 1) // 3 + 1} {pe.year}"
        # reaction: first full session after the report
        h = tk.history(start=(when - pd.Timedelta(days=7)).date(), end=(when + pd.Timedelta(days=7)).date(), auto_adjust=False)["Close"]
        react = ""
        if len(h) >= 2:
            h.index = h.index.tz_convert("America/New_York")
            amc = when.hour >= 12
            after = h[h.index.normalize() > when.normalize()] if amc else h[h.index.normalize() >= when.normalize()]
            before = h[h.index.normalize() <= when.normalize()] if amc else h[h.index.normalize() < when.normalize()]
            if len(after) and len(before):
                ch = (after.iloc[0] / before.iloc[-1] - 1) * 100
                react = f"המניה {'עלתה' if ch >= 0 else 'ירדה'} ב-{abs(ch):.1f}% במסחר שאחרי הדוח."
        u = U.get(t, {})
        card = {"id": f"{t}-{when:%Y-%m}", "t": t, "co": u.get("co", t), "sector": u.get("sec", ""), "date": f"{when:%Y-%m-%d}",
                "q": qlabel, "epsAct": eps_a, "epsEst": eps_e, "epsYoy": eps_y, "epsBasis": "מתואם",
                "revAct": round(rev, 4) if rev is not None else None, "revEst": None, "revYoy": rev_y,
                "guide": "none", "guideText": "", "note": "", "react": react,
                "ir": f"https://www.earningswhispers.com/epsdetails/{t}", "hook": "", "auto": True}
        if eps_a is None: print(t, "no eps"); continue
        data["reports"].append(card); added += 1
        print("added", t, card["date"], eps_a, eps_e, rev, rev_y, react, flush=True)
    except Exception as e:
        print(t, "failed", type(e).__name__, e, flush=True)

data["reports"].sort(key=lambda r: str(r.get("date", "")), reverse=True)
p.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
print("added", added, "of", len(todo))
