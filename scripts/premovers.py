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
        if q.get("symbol") in ("BRBR",): print("debug", {k: q.get(k) for k in ("symbol", "preMarketPrice", "preMarketChangePercent", "regularMarketPrice", "averageDailyVolume3Month", "exchange", "quoteType", "marketState")})
        if ch is None or ch < 9 or (pre or 0) < 5: continue
        if (q.get("averageDailyVolume3Month") or 0) < 800_000 or q.get("exchange") not in EX or q.get("quoteType") != "EQUITY": continue
        rows.append({"t": q["symbol"].replace(".", "-"), "n": q.get("shortName") or q["symbol"], "p": round(float(ch), 1)})
    if not qs or off + 250 >= (r or {}).get("total", 0): break
rows.sort(key=lambda x: -x["p"])
il = dt.datetime.now(ZoneInfo("Asia/Jerusalem")); ny = dt.datetime.now(ZoneInfo("America/New_York"))
print("with pre-market price", npre, "top", sorted(best, reverse=True)[:8])
print("state", state, "seen", seen, "pre movers", [(x["t"], x["p"]) for x in rows])
if state in ("PRE", "PREPRE") or ny.hour * 60 + ny.minute < 9 * 60 + 30:
    data["movers"] = {"asOf": f"{il.day}.{il.month}.{il.year} בשעה {il:%H:%M} (שעון ישראל) · מסחר מקדים", "pre": True,
                      "date": ny.strftime("%Y-%m-%d"), "rows": rows[:40], "down": []}
    p.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
