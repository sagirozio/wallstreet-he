"""Live quotes for every stock on the site, refreshed every 5 minutes during the US session.

Runs inside one long GitHub Actions job (live.yml) that loops until the market closes.
Each round: Yahoo screener (US, cap > $1B, ~12 pages of 250) -> live.json
{"asOf": "DD.MM.YYYY · HH:MM" (Israel), "date": "YYYY-MM-DD", "state": "REGULAR|PRE|POST|CLOSED", "q": {T: [price, change%, dayHigh, dayLow]}}
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

EXT = {}   # extended hours: {T: [price, change% vs the regular close]} (after-hours 16:00-20:00 ET)
def round_once():
    out, state, last_ts = {}, None, 0
    EXT.clear()
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
            h, l = q.get("regularMarketDayHigh"), q.get("regularMarketDayLow")
            if h and l: out[t] += [round(float(h), 2), round(float(l), 2)]   # today's range (52-week highs/lows intraday)
            pp, pc = q.get("postMarketPrice"), q.get("postMarketChangePercent")
            if pp and pc is not None and q.get("postMarketTime", 0) >= q.get("regularMarketTime", 0): EXT[t] = [round(float(pp), 2), round(float(pc), 2)]
            state = state or q.get("marketState")
            last_ts = max(last_ts, int(q.get("regularMarketTime") or 0))
        total = (r or {}).get("total", 0)
        if not quotes or off + 250 >= total:
            break
    missing = sorted(universe - set(out)) if universe else []
    if missing:   # not returned by the screener this round: fetch them directly (batches of 100)
        for i in range(0, len(missing), 100):
            try:
                px = yf.download(missing[i:i+100], period="5d", interval="1d", progress=False, threads=True, auto_adjust=False)
                df = px["Close"]
                for t in df.columns:
                    c = df[t].dropna()
                    if len(c) >= 2:
                        out[t] = [round(float(c.iloc[-1]), 2), round(float((c.iloc[-1] / c.iloc[-2] - 1) * 100), 2)]
                        try: out[t] += [round(float(px["High"][t].loc[c.index[-1]]), 2), round(float(px["Low"][t].loc[c.index[-1]]), 2)]
                        except Exception: pass
            except Exception as e:
                print("download batch failed", type(e).__name__, flush=True)
        print("filled from download:", len(set(missing) & set(out)), "of", len(missing), flush=True)
    return out, state, last_ts

def publish(payload):
    with tempfile.TemporaryDirectory() as d:
        (pathlib.Path(d) / "live.json").write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        run = lambda *a: subprocess.run(["git", *a], cwd=d, check=True, capture_output=True)
        run("init", "-q"); run("checkout", "-q", "--orphan", "live")
        run("-c", "user.name=wallstreet-bot", "-c", "user.email=bot@users.noreply.github.com", "add", "live.json")
        run("-c", "user.name=wallstreet-bot", "-c", "user.email=bot@users.noreply.github.com", "commit", "-qm", "live quotes")
        run("push", "-fq", f"https://x-access-token:{TOKEN}@github.com/{REPO}.git", "live")

# ---- real-time S&P 500 sector averages from Finnhub (free tier: 60 calls/min -> full pass of ~500 members every ~9 min) ----
import threading, io, csv, urllib.request, urllib.parse
FKEY = os.environ.get("FINNHUB_KEY", "").strip()
GICS = {"Information Technology": "XLK", "Communication Services": "XLC", "Consumer Discretionary": "XLY",
        "Consumer Staples": "XLP", "Energy": "XLE", "Financials": "XLF", "Health Care": "XLV",
        "Industrials": "XLI", "Real Estate": "XLRE", "Materials": "XLB", "Utilities": "XLU"}
SPX = {}
FH = {}          # symbol -> day change % (real time)
FHP = {}         # symbol -> price (backup when Yahoo fails)
FH_T = [0.0]     # time of the last completed pass
def finnhub_loop():
    try:
        raw = urllib.request.urlopen("https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv", timeout=60).read().decode()
        for row in csv.DictReader(io.StringIO(raw)): SPX[row["Symbol"]] = GICS.get(row["GICS Sector"])
    except Exception as e:
        print("spx list failed", e, flush=True); return
    while True:
        for sym in list(SPX):
            t0 = time.time()
            try:
                url = "https://finnhub.io/api/v1/quote?" + urllib.parse.urlencode({"symbol": sym, "token": FKEY})
                with urllib.request.urlopen(url, timeout=15) as r: q = json.loads(r.read().decode())
                if q.get("dp") is not None and q.get("c"): FH[sym] = float(q["dp"]); FHP[sym] = [round(float(q["c"]), 2), round(float(q["dp"]), 2)] + ([round(float(q["h"]), 2), round(float(q["l"]), 2)] if q.get("h") and q.get("l") else [])
            except Exception as e:
                if "429" in str(e): time.sleep(30)
            time.sleep(max(0, 1.05 - (time.time() - t0)))
        FH_T[0] = time.time()
def sectors_now():
    out = {}
    for sym, etf in SPX.items():
        if etf and sym in FH: out.setdefault(etf, []).append(FH[sym])
    return {etf: [round(sum(v) / len(v), 2), len(v)] for etf, v in out.items() if len(v) >= 5}
if FKEY:
    threading.Thread(target=finnhub_loop, daemon=True).start()

start = time.time()
while True:
    ny = dt.datetime.now(NY)
    mins = ny.hour * 60 + ny.minute
    weekday = ny.weekday() < 5
    if not ONCE:
        if not weekday or mins > 20 * 60 + 5:
            print("done"); break
        if time.time() - start > 352 * 60:   # GitHub's 6-hour job limit: continue in a new run
            print("job limit: starting a new run", flush=True)
            subprocess.run(f'gh api -X POST repos/{REPO}/actions/workflows/live.yml/dispatches -f ref=main', shell=True)
            break
        if mins < 9 * 60 + 25:
            time.sleep(60); continue
    t0 = time.time()
    try:
        q, state, last_ts = round_once()
        now = dt.datetime.now(IL)
        if len(q) < 500 and len(FHP) > 300:   # Yahoo failed / blocked: S&P 500 prices from Finnhub so the site keeps moving
            print("Yahoo returned", len(q), "quotes -> Finnhub backup for", len(FHP), flush=True)
            q = {**{s_.replace(".", "-"): v for s_, v in FHP.items()}, **q}; last_ts = last_ts or int(time.time())
        if q:
            # "date" = the trading session the prices belong to (not today's date before the open)
            sess = dt.datetime.fromtimestamp(last_ts, NY).strftime("%Y-%m-%d") if last_ts else dt.datetime.now(NY).strftime("%Y-%m-%d")
            payload = {"asOf": now.strftime("%d.%m.%Y · %H:%M"), "date": sess, "state": state or ("REGULAR" if 9 * 60 + 30 <= mins < 16 * 60 else "POST" if mins >= 16 * 60 else "PRE"), "q": q}
            if FH: payload["sec"] = sectors_now(); payload["secN"] = len(FH)
            ix = {}
            for sym in ("^GSPC", "^IXIC", "^DJI"):   # index levels for the "market in 30 seconds" line
                try:
                    fi = yf.Ticker(sym).fast_info; lp, pc = fi.last_price, fi.previous_close
                    if lp and pc: ix[sym] = [round(float(lp), 2), round((float(lp) / float(pc) - 1) * 100, 2)]
                except Exception as e: print("index", sym, type(e).__name__, flush=True)
            if ix: payload["idx"] = ix
            etf = {}
            try:
                px = yf.download(["XLK", "XLC", "XLY", "XLP", "XLE", "XLF", "XLV", "XLI", "XLRE", "XLB", "XLU"], period="5d", interval="1d", progress=False, auto_adjust=False, threads=True)["Close"]
                for e in px.columns:
                    c = px[e].dropna()
                    if len(c) >= 2: etf[e] = [round(float(c.iloc[-1]), 2), round(float((c.iloc[-1] / c.iloc[-2] - 1) * 100), 2)]
            except Exception as e: print("etf", type(e).__name__, flush=True)
            if etf: payload["etf"] = etf   # sector ETF price + change (XLK, XLF ...)
            if EXT and mins >= 16 * 60: payload["post"] = dict(EXT)   # after-hours prices (16:00-20:00 New York)
            if mins >= 16 * 60:   # after-hours for the index ETFs (status line on the home page)
                pi = {}
                for sym in ("SPY", "QQQ", "DIA"):
                    try:
                        inf = yf.Ticker(sym).info; pp, pc = inf.get("postMarketPrice"), inf.get("postMarketChangePercent")
                        if pp and pc is not None: pi[sym] = [round(float(pp), 2), round(float(pc), 2)]
                    except Exception as e: print("post", sym, type(e).__name__, flush=True)
                if pi: payload["postIdx"] = pi
            publish(payload)
        print(now.strftime("%H:%M"), state, len(q), "quotes", f"{time.time() - t0:.0f}s", flush=True)
    except Exception as e:
        print("round failed", type(e).__name__, e, flush=True)
    if ONCE:
        break
    time.sleep(max(30, (180 if mins < 16 * 60 + 5 else 600) - (time.time() - t0)))   # every 3 min in the session, 10 min after-hours
