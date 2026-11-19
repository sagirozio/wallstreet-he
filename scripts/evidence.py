"""Evidence-based market indicators -> data.json["evidence"] (market page, "מחקר מבוסס ראיות").

  vix   : VIX (30 days) vs VIX3M (3 months). Inverted (VIX above VIX3M) = short-term fear above long-term fear.
          history: every new inversion since 2007 (after 20+ normal sessions) and what the S&P 500 did 1, 3 and 6 months later.
  hy    : high-yield credit spread (ICE BofA US High Yield OAS, FRED BAMLH0A0HYM2), last value, 1-year range, percentile since 1997, weekly line.
  fg    : fear / greed gauge 0-100 from 5 parts we compute ourselves (each 0-100, 50 = normal):
          momentum (S&P 500 vs its 125-day average), VIX vs its 1-year range, credit spread vs its 1-year range,
          breadth (% of S&P 500 stocks above the 50-day average, from our breadth table), 52-week highs vs lows (our breadth table).
  season: S&P 500 average return and % of positive years for each calendar month since 1950, and this month's.
All numbers are history, not a forecast. Runs in the nightly update.
"""
import json, pathlib, io, urllib.request, datetime as dt
import pandas as pd
import yfinance as yf

root = pathlib.Path(__file__).resolve().parent.parent
p = root / "data.json"
data = json.loads(p.read_text(encoding="utf-8"))
E = {"asOf": dt.date.today().isoformat()}

def closes(sym, start):
    s = yf.download(sym, start=start, progress=False, auto_adjust=False)["Close"]
    if isinstance(s, pd.DataFrame): s = s.iloc[:, 0]
    return s.dropna()

# ---------- S&P 500 (long history) ----------
spx = closes("^GSPC", "1950-01-01")

# ---------- VIX term structure ----------
try:
    vix, v3 = closes("^VIX", "2007-01-01"), closes("^VIX3M", "2007-01-01")
    df = pd.concat([vix.rename("v"), v3.rename("v3"), spx.rename("s")], axis=1).dropna()
    df["r"] = df["v"] / df["v3"]
    inv = df["r"] > 1
    ev, last_inv = [], None
    for i in range(20, len(df)):
        if inv.iloc[i] and not inv.iloc[i - 20:i].any():
            d = df.index[i]; s0 = df["s"].iloc[i]
            fw = {}
            for k, n in (("m1", 21), ("m3", 63), ("m6", 126)):
                if i + n < len(df): fw[k] = round((df["s"].iloc[i + n] / s0 - 1) * 100, 1)
            ev.append({"d": str(d.date()), "vix": round(float(df["v"].iloc[i]), 1), **fw})
    done6 = [e["m6"] for e in ev if "m6" in e]
    E["vix"] = {"v": round(float(df["v"].iloc[-1]), 2), "v3": round(float(df["v3"].iloc[-1]), 2), "r": round(float(df["r"].iloc[-1]), 3),
                "inv": bool(inv.iloc[-1]), "date": str(df.index[-1].date()),
                "line": [round(float(x), 3) for x in df["r"].iloc[-250:].iloc[::5]],
                "ev": ev[-12:][::-1], "n": len(ev),
                "avg6": round(sum(done6) / len(done6), 1) if done6 else None,
                "pos6": round(sum(1 for x in done6 if x > 0) / len(done6) * 100) if done6 else None}
    print("vix", E["vix"]["v"], E["vix"]["v3"], "inverted" if E["vix"]["inv"] else "normal", "events", len(ev))
except Exception as e: print("vix failed", type(e).__name__, e)

# ---------- high-yield credit spread (FRED) ----------
try:
    raw = urllib.request.urlopen("https://fred.stlouisfed.org/graph/fredgraph.csv?id=BAMLH0A0HYM2", timeout=60).read().decode()
    h = pd.read_csv(io.StringIO(raw))
    h.columns = ["d", "v"]; h["v"] = pd.to_numeric(h["v"], errors="coerce"); h = h.dropna(); h["d"] = pd.to_datetime(h["d"]); h = h.set_index("d")["v"]
    y1 = h[h.index >= h.index[-1] - pd.Timedelta(days=365)]
    E["hy"] = {"v": round(float(h.iloc[-1]), 2), "date": str(h.index[-1].date()), "lo": round(float(y1.min()), 2), "hi": round(float(y1.max()), 2),
               "pct": round(float((h < h.iloc[-1]).mean() * 100)), "m1": round(float(h.iloc[-1] - h.iloc[-22]), 2) if len(h) > 22 else None,
               "line": [round(float(x), 2) for x in y1.iloc[::5]], "since": str(h.index[0].year)}
    print("hy", E["hy"])
except Exception as e: print("hy failed", type(e).__name__, e)

# ---------- fear / greed gauge (our own 5 parts) ----------
def scale(x, lo, hi, invert=False):
    if x is None or lo is None or hi is None or hi <= lo: return None
    v = max(0.0, min(100.0, (x - lo) / (hi - lo) * 100))
    return round(100 - v if invert else v)
parts = {}
try:
    s = spx.iloc[-260:]; ma = spx.rolling(125).mean()
    dev = (spx / ma - 1) * 100; d1 = dev.iloc[-260:]
    parts["mom"] = {"v": round(float(dev.iloc[-1]), 1), "s": scale(float(dev.iloc[-1]), float(d1.min()), float(d1.max()))}
except Exception as e: print("mom", e)
if E.get("vix"):
    v1 = vix.iloc[-260:]; parts["vix"] = {"v": E["vix"]["v"], "s": scale(float(vix.iloc[-1]), float(v1.min()), float(v1.max()), invert=True)}
if E.get("hy"):
    parts["hy"] = {"v": E["hy"]["v"], "s": scale(E["hy"]["v"], E["hy"]["lo"], E["hy"]["hi"], invert=True)}
rows = (data.get("breadth") or {}).get("rows") or []
if rows:
    r0 = rows[0]
    if r0.get("ma50") is not None: parts["br"] = {"v": r0["ma50"], "s": round(max(0, min(100, r0["ma50"])))}
    hi, lo = r0.get("hi") or 0, r0.get("lo") or 0
    if hi + lo: parts["hl"] = {"v": [hi, lo], "s": round(hi / (hi + lo) * 100)}
ok = [x["s"] for x in parts.values() if x.get("s") is not None]
if len(ok) >= 3:
    sc = round(sum(ok) / len(ok))
    E["fg"] = {"s": sc, "parts": parts, "lbl": "פחד קיצוני" if sc < 20 else "פחד" if sc < 40 else "ניטרלי" if sc <= 60 else "חמדנות" if sc <= 80 else "חמדנות קיצונית"}
    print("fear/greed", sc, {k: v.get("s") for k, v in parts.items()})

# ---------- seasonality ----------
try:
    m = spx.resample("ME").last().pct_change().dropna() * 100
    tbl = []
    for mo in range(1, 13):
        x = m[m.index.month == mo]
        tbl.append({"m": mo, "avg": round(float(x.mean()), 2), "pos": round(float((x > 0).mean() * 100)), "n": int(len(x))})
    E["season"] = {"since": int(m.index[0].year), "t": tbl, "now": dt.date.today().month}
except Exception as e: print("season failed", e)

data["evidence"] = E
p.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
print("evidence written", list(E))
