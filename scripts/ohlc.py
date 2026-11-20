"""Daily OHLC + volume for the own candlestick chart (stock page, below the TradingView chart).
Only the tickers in TICKERS for now. Writes ohlc/<T>.json = {"t","d":[dates],"o","h","l","c","v"} (~14 months, split-adjusted, not dividend-adjusted).
Fail-soft: on any error the existing file stays."""
import json, pathlib
import yfinance as yf

root = pathlib.Path(__file__).resolve().parent.parent
TICKERS = ["NVDA"]
out = root / "ohlc"; out.mkdir(exist_ok=True)
for t in TICKERS:
    try:
        df = yf.download(t, period="14mo", interval="1d", auto_adjust=False, progress=False, threads=False)
        if hasattr(df.columns, "levels"): df.columns = df.columns.get_level_values(0)
        df = df.dropna(subset=["Open", "High", "Low", "Close"])
        if len(df) < 100: print(t, "too few rows", len(df)); continue
        r = lambda c: [round(float(x), 2) for x in df[c]]
        j = {"t": t, "d": [d.strftime("%Y-%m-%d") for d in df.index], "o": r("Open"), "h": r("High"), "l": r("Low"), "c": r("Close"), "v": [int(x) for x in df["Volume"].fillna(0)]}
        (out / f"{t}.json").write_text(json.dumps(j, separators=(",", ":")), encoding="utf-8")
        print(t, "ohlc", len(j["d"]), j["d"][-1])
    except Exception as e:
        print(t, "ohlc failed", type(e).__name__, e)
