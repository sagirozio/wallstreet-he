"""Bitcoin / Ethereum performance for the crypto pages -> data.json["crypto"].
{asOf, rows: {"BTC-USD": {p, d, w, m, q, h, ytd, y}}}: price and % change vs the previous daily close, 7, 30, 91, 182 days ago,
the last close of the previous year and 365 days ago (crypto trades every day, so the periods are calendar days).
Called from premarket.py (every round of the loop, published on the intra branch) and from the nightly update."""
import json, pathlib, datetime as dt
from zoneinfo import ZoneInfo

SYMS = ("BTC-USD", "ETH-USD")

def calc():
    import yfinance as yf
    px = yf.download(list(SYMS), period="2y", interval="1d", progress=False, auto_adjust=False, threads=True)["Close"]
    rows = {}
    for s in SYMS:
        c = px[s].dropna()
        if len(c) < 30: continue
        last, day = float(c.iloc[-1]), c.index[-1]
        def ago(days):
            h = c[c.index <= day - dt.timedelta(days=days)]
            return float(h.iloc[-1]) if len(h) else None
        prev_year = c[c.index.year < day.year]
        base = {"d": float(c.iloc[-2]), "w": ago(7), "m": ago(30), "q": ago(91), "h": ago(182),
                "ytd": float(prev_year.iloc[-1]) if len(prev_year) else None, "y": ago(365)}
        r = {"p": round(last, 2)}
        for k, b in base.items():
            if b and b > 0:
                v = (last / b - 1) * 100
                if abs(v) < 2000: r[k] = round(v, 1)
        rows[s] = r
    if not rows: return None
    return {"asOf": dt.datetime.now(ZoneInfo("Asia/Jerusalem")).strftime("%d.%m.%Y · %H:%M"), "rows": rows}

if __name__ == "__main__":
    p = pathlib.Path(__file__).resolve().parent.parent / "data.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    out = calc()
    if out:
        data["crypto"] = out
        p.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print("crypto", out)
