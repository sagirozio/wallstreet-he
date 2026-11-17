"""Pre-market (and after-hours) quotes for SPY and QQQ -> data.json["premarket"].

Runs every 15 minutes before the US open (GitHub Actions, premarket.yml). Light: two Yahoo requests.
"""
import json, pathlib, datetime as dt
from zoneinfo import ZoneInfo
import yfinance as yf

root = pathlib.Path(__file__).resolve().parent.parent
p = root / "data.json"
data = json.loads(p.read_text(encoding="utf-8"))

rows, state = [], None
for sym, name in (("SPY", "S&P 500"), ("QQQ", "נאסד״ק 100")):
    try:
        i = yf.Ticker(sym).info or {}
    except Exception as e:
        print("fail", sym, e); continue
    state = i.get("marketState") or state
    prev = i.get("regularMarketPreviousClose") or i.get("previousClose")
    pre, post = i.get("preMarketPrice"), i.get("postMarketPrice")
    if state in ("PRE", "PREPRE") and pre:
        px, ch = pre, i.get("preMarketChangePercent")
        if ch is None and prev: ch = (pre / prev - 1) * 100
        kind = "pre"
    elif state in ("POST", "POSTPOST") and post:
        reg = i.get("regularMarketPrice") or prev
        px, ch = post, i.get("postMarketChangePercent")
        if ch is None and reg: ch = (post / reg - 1) * 100
        kind = "post"
    else:
        continue
    rows.append({"t": sym, "n": name, "p": round(float(px), 2), "c": round(float(ch or 0), 2), "kind": kind})

now = dt.datetime.now(ZoneInfo("Asia/Jerusalem"))
data["premarket"] = {"state": state, "asOf": now.strftime("%d.%m.%Y · %H:%M"), "date": now.strftime("%Y-%m-%d"), "rows": rows}
p.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
print("premarket", state, rows)
