"""Live quotes for every stock on the site, refreshed every 5 minutes during the US session.

Runs inside one long GitHub Actions job (live.yml) that loops until the market closes.
Each round: Yahoo screener (US, cap > $1B, ~12 pages of 250) -> live.json
{"asOf": "DD.MM.YYYY · HH:MM" (Israel), "date": "YYYY-MM-DD", "state": "REGULAR|PRE|POST|CLOSED", "q": {T: [price, change%]}}
pushed as a single commit to the `live` branch (force-push, so it never grows the history).
The page reads it from raw.githubusercontent.com.

ONCE=1 -> one round and exit (manual runs).
"""
import json, os, pathlib, subprocess, tempfile, time, datetime as dt
from zoneinfo import ZoneInfo
import yfinance as yf
from yfinance import EquityQuery

root = pathlib.Path(__file__).resolve().parent.parent
NY, IL = ZoneInfo("America/New_York"), ZoneInfo("Asia/Jerusalem")
ONCE = os.environ.get("ONCE") == "1"
REPO = os.environ.get("GITHUB_REPOSITORY", "sagirozio/wallstreet-he")
TOKEN = os.environ.get("GH_TOKEN", "")

universe = set()
try:
    universe = {s[0] for lst in json.loads((root / "stocks.json").read_text(encoding="utf-8"))["stocks"].values() for s in lst}
except Exception as e:
    print("no stocks.json", e)

Q = EquityQuery("and", [EquityQuery("eq", ["region", "us"]), EquityQuery("gt", ["intradaymarketcap", 1_000_000_000])])

def round_once():
    out, state, last_ts = {}, None, 0
    for off in range(0, 4000, 250):
        r = None
        for k in range(3):
            try:
                r = yf.screen(Q, offset=off, size=250, sortField="intradaymarketcap", sortAsc=False); break
            except Exception as e:
                print("screen retry", off, type(e).__name__, flush=True); time.sleep(5 * (k + 1))
        quotes = (r or {}).get("quotes", [])
        for q in quotes:
            t = (q.get("symbol") or "").replace(".", "-")
            if universe and t not in universe:
                continue
            p, c = q.get("regularMarketPrice"), q.get("regularMarketChangePercent")
            if p is None or c is None:
                continue
            out[t] = [round(float(p), 2), round(float(c), 2)]
            state = state or q.get("marketState")
            last_ts = max(last_ts, int(q.get("regularMarketTime") or 0))
        if len(quotes) < 250:
            break
    return out, state, last_ts

def publish(payload):
    with tempfile.TemporaryDirectory() as d:
        (pathlib.Path(d) / "live.json").write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        run = lambda *a: subprocess.run(["git", *a], cwd=d, check=True, capture_output=True)
        run("init", "-q"); run("checkout", "-q", "--orphan", "live")
        run("-c", "user.name=wallstreet-bot", "-c", "user.email=bot@users.noreply.github.com", "add", "live.json")
        run("-c", "user.name=wallstreet-bot", "-c", "user.email=bot@users.noreply.github.com", "commit", "-qm", "live quotes")
        run("push", "-fq", f"https://x-access-token:{TOKEN}@github.com/{REPO}.git", "live")

start = time.time()
while True:
    ny = dt.datetime.now(NY)
    mins = ny.hour * 60 + ny.minute
    weekday = ny.weekday() < 5
    if not ONCE:
        if not weekday or mins > 16 * 60 + 10 or time.time() - start > 352 * 60:
            print("done"); break
        if mins < 9 * 60 + 25:
            time.sleep(60); continue
    t0 = time.time()
    try:
        q, state, last_ts = round_once()
        now = dt.datetime.now(IL)
        if q:
            # "date" = the trading session the prices belong to (not today's date before the open)
            sess = dt.datetime.fromtimestamp(last_ts, NY).strftime("%Y-%m-%d") if last_ts else dt.datetime.now(NY).strftime("%Y-%m-%d")
            publish({"asOf": now.strftime("%d.%m.%Y · %H:%M"), "date": sess, "state": state or "", "q": q})
        print(now.strftime("%H:%M"), state, len(q), "quotes", f"{time.time() - t0:.0f}s", flush=True)
    except Exception as e:
        print("round failed", type(e).__name__, e, flush=True)
    if ONCE:
        break
    time.sleep(max(30, 300 - (time.time() - t0)))
