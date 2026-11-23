"""Pre-market 9%+ movers (from the pre-market open, 04:00 New York): Yahoo screener over US stocks above $1B and $5, pre-market change >= 9%,
avg volume >= 800k, major exchanges -> data.json["movers"] with "pre": true (replaced by the regular movers at the open)."""
import json, pathlib, datetime as dt, time
from zoneinfo import ZoneInfo
import yfinance as yf
from yfinance import EquityQuery
root = pathlib.Path(__file__).resolve().parent.parent
p = root / "data.json"; data = json.loads(p.read_text(encoding="utf-8"))
EX = {"NMS", "NGM", "NCM", "NYQ", "ASE", "PCX", "BTS"}
# only the major exchanges: without this the US region holds 4,000+ names above $1B (OTC foreign listings) and smaller real stocks fell off the end
try: Q = EquityQuery("and", [EquityQuery("eq", ["region", "us"]), EquityQuery("gt", ["intradaymarketcap", 1_000_000_000]), EquityQuery("is-in", ["exchange", "NMS", "NGM", "NCM", "NYQ", "ASE", "PCX", "BTS"])])
except Exception as e:
    print("exchange filter unavailable", type(e).__name__, e)
    Q = EquityQuery("and", [EquityQuery("eq", ["region", "us"]), EquityQuery("gt", ["intradaymarketcap", 1_000_000_000])])
rows, seen, state, npre, best = [], 0, None, 0, []
UNI = {s_[0] for l_ in ((data.get("themes") or {}).get("stocks") or {}).values() for s_ in l_}
PM = {}   # pre-market price of every stock on the site: {T: [price, change % vs the last close]} -> data["premkt"] (shown on the stock page until the open)
for off in range(0, 7000, 250):
    r = None
    for k in range(3):
        try: r = yf.screen(Q, offset=off, size=250, sortField="intradaymarketcap", sortAsc=False); break
        except Exception as e: print("retry", off, type(e).__name__); time.sleep(5 * (k + 1))
    qs = (r or {}).get("quotes", [])
    for q in qs:
        seen += 1; state = state or q.get("marketState")
        pre, base = q.get("preMarketPrice"), q.get("regularMarketPrice")
        ch = q.get("preMarketChangePercent")
        if ch is None and pre and base: ch = (pre / base - 1) * 100
        if pre: npre += 1; best.append((round(ch or 0, 1), q["symbol"]))
        if pre and ch is not None and q["symbol"].replace(".", "-") in UNI: PM[q["symbol"].replace(".", "-")] = [round(float(pre), 2), round(float(ch), 2)]
        if ch is None or ch < 9 or (pre or 0) < 5: continue
        if (q.get("averageDailyVolume3Month") or 0) < 800_000 or q.get("exchange") not in EX or q.get("quoteType") != "EQUITY": continue
        r_ = {"t": q["symbol"].replace(".", "-"), "n": q.get("shortName") or q["symbol"], "p": round(float(ch), 1)}
        rows.append(r_)
    if not qs or off + 250 >= (r or {}).get("total", 0): break
rows.sort(key=lambda x: -x["p"])
# pre-market volume of each mover today (the screener has no such field): 5-minute bars with the extended hours, summed from 04:00 to 09:30 New York.
# The home page ranks the pre-market movers by it.
if rows:
    try:
        import pandas as pd
        tk = [x["t"] for x in rows[:40]]
        bars = yf.download(tk, period="1d", interval="5m", prepost=True, group_by="column", threads=True, progress=False, auto_adjust=False)
        vol = bars["Volume"] if "Volume" in bars else None
        if vol is not None:
            if isinstance(vol, pd.Series): vol = vol.to_frame(tk[0])
            idx = vol.index.tz_convert("America/New_York") if vol.index.tz is not None else vol.index
            today_ = dt.datetime.now(ZoneInfo("America/New_York")).date()
            pre_ = [(i.date() == today_ and (i.hour, i.minute) < (9, 30)) for i in idx]
            sums = vol[pre_].sum()
            for x in rows:
                v_ = sums.get(x["t"]) if hasattr(sums, "get") else None
                if v_ is not None and v_ == v_ and v_ > 0: x["v"] = int(v_)
        print("pre-market volume", [(x["t"], x.get("v")) for x in rows[:10]])
    except Exception as e:
        print("pre-market volume failed", type(e).__name__, e)
il = dt.datetime.now(ZoneInfo("Asia/Jerusalem")); ny = dt.datetime.now(ZoneInfo("America/New_York"))
print("with pre-market price", npre, "top", sorted(best, reverse=True)[:8])
print("state", state, "seen", seen, "pre movers", [(x["t"], x["p"]) for x in rows])
if state in ("PRE", "PREPRE") or ny.hour * 60 + ny.minute < 9 * 60 + 30:
    data["movers"] = {"asOf": f"{il.day}.{il.month}.{il.year} בשעה {il:%H:%M} (שעון ישראל) · מסחר מקדים", "pre": True,
                      "date": ny.strftime("%Y-%m-%d"), "rows": rows[:40], "down": []}
    data["premkt"] = {"date": ny.strftime("%Y-%m-%d"), "asOf": f"{il:%H:%M}", "q": PM}
    p.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
