"""Sector returns the way Google Finance / TradingView show them: the price change of each SPDR sector ETF
(XLK, XLF, ...), unadjusted closes, calendar periods:
  d   = last price vs the previous close        w  = vs the close 7 calendar days earlier
  m   = vs one calendar month earlier           q  = 3 months     h = 6 months
  ytd = vs the last close of the previous year  y  = 1 year
The base is the last close on or before that date. Used by update.py (nightly) and update_live.py (every round in the session)."""
import datetime as dt

ETFS = ["XLK", "XLC", "XLY", "XLP", "XLE", "XLF", "XLV", "XLI", "XLRE", "XLB", "XLU"]

def returns():
    import yfinance as yf
    import pandas as pd
    px = yf.download(ETFS, period="2y", interval="1d", progress=False, auto_adjust=False, threads=True)["Close"]
    out = {}
    for e in ETFS:
        if e not in px.columns: continue
        c = px[e].dropna()
        if len(c) < 260: continue
        last_day, last = c.index[-1], float(c.iloc[-1])
        def base(d):
            h = c[c.index <= pd.Timestamp(d)]
            return float(h.iloc[-1]) if len(h) else None
        ld = last_day.date()
        def months(n):
            y, m = ld.year, ld.month - n
            while m <= 0: m += 12; y -= 1
            import calendar
            return dt.date(y, m, min(ld.day, calendar.monthrange(y, m)[1]))
        b = {"d": float(c.iloc[-2]), "w": base(ld - dt.timedelta(days=7)), "m": base(months(1)), "q": base(months(3)),
             "h": base(months(6)), "ytd": base(dt.date(ld.year - 1, 12, 31)), "y": base(months(12))}
        out[e] = {k: round((last / v - 1) * 100, 2) for k, v in b.items() if v}
        out[e]["px"] = round(last, 2)
        y0 = c[c.index <= pd.Timestamp(dt.date(ld.year - 1, 12, 31))]
        ytd = c[c.index >= y0.index[-1]] if len(y0) else c[c.index.year == ld.year]
        pts = list(range(0, len(ytd), 5)); pts = pts if pts[-1] == len(ytd) - 1 else pts + [len(ytd) - 1]
        out[e]["sp"] = [round(float(ytd.iloc[i]), 2) for i in pts]   # year-to-date line for the tables
    return out

def apply(data):
    """Overwrite the return fields of data["sectors"]["rows"] with the ETF returns; True when done."""
    try:
        R = returns()
    except Exception as e:
        print("sector ETF returns failed", type(e).__name__, e); return False
    n = 0
    for row in (data.get("sectors") or {}).get("rows", []):
        r = R.get(row.get("t"))
        if not r: continue
        for k in ("d", "w", "m", "q", "h", "ytd", "y", "sp"):
            if k in r: row[k] = r[k]
        n += 1
    print("sector ETF returns", n, {k: R[k].get("m") for k in list(R)[:3]})
    return n >= 8

if __name__ == "__main__":
    for k, v in returns().items(): print(k, v)
