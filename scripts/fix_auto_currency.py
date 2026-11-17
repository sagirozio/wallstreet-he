"""Auto cards: revenue for companies that report in a non-USD currency is not comparable -> keep YoY %, drop the amount."""
import json, pathlib, yfinance as yf
p = pathlib.Path(__file__).resolve().parent.parent / "data.json"; d = json.loads(p.read_text(encoding="utf-8"))
n = 0
for r in d["reports"]:
    if not r.get("auto") or r.get("revAct") is None: continue
    try: cur = (yf.Ticker(r["t"]).info or {}).get("financialCurrency") or "USD"
    except Exception: continue
    if cur != "USD":
        r["revAct"] = None; r["revCur"] = cur; n += 1; print(r["t"], cur, flush=True)
# GOOG duplicates GOOGL
d["reports"] = [r for r in d["reports"] if not (r.get("auto") and r["t"] == "GOOG")]
p.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8"); print("fixed", n)
