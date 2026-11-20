"""Thematic ETFs page (מחקר → תעודות סל): returns of a fixed list of theme ETFs and each fund's top holdings.

Prices and holdings from Yahoo (yfinance): history for the returns, Ticker.funds_data.top_holdings for the holdings.
Holdings change slowly, so they are refreshed only when older than 7 days (or missing). Writes data.json["etfs"].
"""
import json, pathlib, datetime as dt
import pandas as pd, yfinance as yf

root = pathlib.Path(__file__).resolve().parent.parent
# (ticker, Hebrew theme, group)
ETFS = [
    ("SMH", "שבבים", "טכנולוגיה"), ("IGV", "תוכנה", "טכנולוגיה"), ("CIBR", "סייבר", "טכנולוגיה"), ("SKYY", "ענן", "טכנולוגיה"),
    ("AIQ", "בינה מלאכותית", "טכנולוגיה"), ("BOTZ", "רובוטיקה ואוטומציה", "טכנולוגיה"), ("QTUM", "מחשוב קוונטי", "טכנולוגיה"),
    ("ARKK", "חדשנות (ARK)", "טכנולוגיה"), ("UFO", "חלל", "טכנולוגיה"), ("SOCL", "רשתות חברתיות", "טכנולוגיה"),
    ("URA", "אורניום וגרעין", "אנרגיה"), ("TAN", "אנרגיה סולארית", "אנרגיה"), ("ICLN", "אנרגיה נקייה", "אנרגיה"),
    ("XOP", "חיפוש והפקת נפט וגז", "אנרגיה"), ("OIH", "שירותי נפט", "אנרגיה"), ("LIT", "ליתיום וסוללות", "אנרגיה"),
    ("XBI", "ביוטק", "בריאות"), ("IHI", "מכשור רפואי", "בריאות"), ("XPH", "תרופות", "בריאות"),
    ("KRE", "בנקים אזוריים", "פיננסים"), ("KBE", "בנקים", "פיננסים"), ("IAI", "ברוקרים ובורסות", "פיננסים"),
    ("BLOK", "בלוקצ'יין וקריפטו", "פיננסים"), ("KIE", "ביטוח", "פיננסים"),
    ("ITA", "ביטחון ותעופה", "תעשייה"), ("PAVE", "תשתיות", "תעשייה"), ("JETS", "חברות תעופה", "תעשייה"),
    ("ITB", "בנייה למגורים", "תעשייה"), ("XTN", "תחבורה", "תעשייה"),
    ("XRT", "קמעונאות", "צריכה"), ("PEJ", "פנאי ובידור", "צריכה"),
    ("GDX", "כורי זהב", "סחורות"), ("SIL", "כורי כסף", "סחורות"), ("COPX", "כורי נחושת", "סחורות"), ("REMX", "מתכות נדירות", "סחורות"),
]

data = json.loads((root / "data.json").read_text(encoding="utf-8"))
old = {e["t"]: e for e in (data.get("etfs") or {}).get("rows", [])}
tick = [t for t, _, _ in ETFS]
px = yf.download(tick, period="14mo", interval="1d", auto_adjust=True, group_by="column", threads=True, progress=False)["Close"]
px.index = px.index.tz_localize(None) if px.index.tz is not None else px.index
today = dt.date.today()
rows = []
for t, he, grp in ETFS:
    c = px[t].dropna() if t in px else pd.Series(dtype=float)
    if len(c) < 30:
        if t in old: rows.append(old[t])
        continue
    last = c.iloc[-1]
    def back(n):
        return round(float((last / c.iloc[-1 - n] - 1) * 100), 2) if len(c) > n else None
    py = c[c.index.year < c.index[-1].year]
    r = {"t": t, "n": he, "g": grp, "p": round(float(last), 2), "d": back(1), "w": back(5), "m": back(21), "q": back(63),
         "ytd": round(float((last / py.iloc[-1] - 1) * 100), 2) if len(py) else None, "y": back(252)}
    o = old.get(t) or {}
    hold, hAt = o.get("h"), o.get("hAt")
    if not hold or not hAt or (today - dt.date.fromisoformat(hAt)).days >= 7:
        try:
            th = yf.Ticker(t).funds_data.top_holdings
            hold = [[str(sym).replace(".", "-"), str(row.get("Name", "") or ""), round(float(row.get("Holding Percent", 0)) * 100, 1)]
                    for sym, row in th.head(10).iterrows()]
            hAt = today.isoformat()
        except Exception as e:
            print("holdings failed", t, type(e).__name__)
    if hold: r["h"], r["hAt"] = hold, hAt
    # ID-card facts (issuer, expense ratio, assets, inception): refreshed weekly with the holdings, kept if Yahoo fails
    inf = o.get("i")
    if not inf or hAt == today.isoformat():
        try:
            i = yf.Ticker(t).info or {}
            er = i.get("netExpenseRatio", i.get("annualReportExpenseRatio"))
            inc = i.get("fundInceptionDate")
            n = {"f": i.get("fundFamily"), "er": round(float(er), 3) if er is not None else None,
                 "aum": round(float(i["totalAssets"]) / 1e9, 2) if i.get("totalAssets") else None,
                 "inc": dt.datetime.utcfromtimestamp(int(inc)).strftime("%Y-%m-%d") if inc else None}
            n = {k: v for k, v in n.items() if v is not None}
            if n: inf = n
        except Exception as e:
            print("info failed", t, type(e).__name__)
    if inf: r["i"] = inf
    rows.append(r)
data["etfs"] = {"asOf": str(px.index[-1].date()), "rows": rows}
(root / "data.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
print("etfs", len(rows), "with holdings", sum(1 for r in rows if r.get("h")))
