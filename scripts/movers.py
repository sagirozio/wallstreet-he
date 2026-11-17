"""Today's 10%+ movers (Yahoo screener) -> data.json["movers"]."""
import json, pathlib, datetime, zoneinfo
import yfinance as yf
root = pathlib.Path(__file__).resolve().parent.parent
data_path = root / "data.json"; data = json.loads(data_path.read_text(encoding="utf-8"))
now = datetime.datetime.now(zoneinfo.ZoneInfo("America/New_York"))
live = now.weekday() < 5 and (9 * 60 + 30) <= now.hour * 60 + now.minute < 16 * 60 + 15
stamp = f"{now.day}.{now.month}.{now.year} בשעה {datetime.datetime.now(zoneinfo.ZoneInfo('Asia/Jerusalem')):%H:%M} (שעון ישראל)" if live else ""
# ---- today's big movers: up 10%+ (cap > $1B, avg volume > 800k, major US exchanges) ----
try:
    r = yf.screen("day_gainers", count=250)
    EX = {"NMS", "NGM", "NCM", "NYQ", "ASE", "PCX", "BTS"}
    mv = []
    for q in r.get("quotes", []):
        p = q.get("regularMarketChangePercent") or 0
        if p >= 10 and (q.get("marketCap") or 0) >= 1e9 and (q.get("averageDailyVolume3Month") or 0) >= 800_000 \
           and q.get("exchange") in EX and q.get("quoteType") == "EQUITY":
            mv.append({"t": q["symbol"], "n": q.get("shortName") or q["symbol"], "p": round(float(p), 1)})
    mv.sort(key=lambda x: -x["p"])
    dn = []
    try:
        r2 = yf.screen("day_losers", count=250)
        for q in r2.get("quotes", []):
            p = q.get("regularMarketChangePercent") or 0
            if p <= -10 and (q.get("marketCap") or 0) >= 1e9 and (q.get("averageDailyVolume3Month") or 0) >= 800_000 \
               and q.get("exchange") in EX and q.get("quoteType") == "EQUITY":
                dn.append({"t": q["symbol"], "n": q.get("shortName") or q["symbol"], "p": round(float(p), 1)})
        dn.sort(key=lambda x: x["p"])
    except Exception as e:
        print("losers failed", e)
    # date the movers by the screener's own quote time (the price history used for `stamp` can lag a day)
    mv_stamp = stamp
    try:
        import datetime as _dt
        ts = max(int(q.get("regularMarketTime") or 0) for q in r.get("quotes", []))
        if ts:
            qd = _dt.datetime.fromtimestamp(ts, _dt.timezone(_dt.timedelta(hours=-5))).date()
            if not live: mv_stamp = f"סגירת {qd.day}.{qd.month}.{qd.year}"
    except Exception as e:
        print("movers time", e)
    data["movers"] = {"asOf": mv_stamp, "rows": mv[:40], "down": dn[:20]}
    print("movers", len(mv))
except Exception as e:
    print("movers failed", e)

data_path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
