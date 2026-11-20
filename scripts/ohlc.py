"""Daily OHLC + volume of every stock on the site (plus the ETFs with a card and the two crypto pages), for our own price chart.

Yahoo (yfinance), 3 years, split-adjusted and not dividend-adjusted. One file per stock:
<T>.json = {"d":[dates],"o":[],"h":[],"l":[],"c":[],"v":[]}, pushed as a single commit to the `ohlc` branch
(orphan, force-pushed like `px`, so it never grows the main history). The page reads it from raw.githubusercontent.com.
A session that is still open is left out (the page draws today's candle from the live quote).
Fail-soft: the files of the previous run are kept for every stock that failed this time; nothing is pushed when nothing came back."""
import json, os, pathlib, subprocess, tempfile, time, datetime as dt
from zoneinfo import ZoneInfo
import yfinance as yf

root = pathlib.Path(__file__).resolve().parent.parent
REPO = os.environ.get("GITHUB_REPOSITORY", "sagirozio/wallstreet-he")
TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
URL = f"https://x-access-token:{TOKEN}@github.com/{REPO}.git" if TOKEN else f"https://github.com/{REPO}.git"

uni = sorted({s[0] for lst in json.loads((root / "stocks.json").read_text(encoding="utf-8"))["stocks"].values() for s in lst})
# besides the stocks: the ETFs that have a card on the site (thematic table, sector funds, index funds) and the two crypto pages
EXTRA = ["XLK", "XLC", "XLY", "XLP", "XLE", "XLF", "XLV", "XLI", "XLRE", "XLB", "XLU", "SPY", "QQQ", "DIA", "IWM", "BTC-USD", "ETH-USD"]
try:
    EXTRA += [r["t"] for r in json.loads((root / "data.json").read_text(encoding="utf-8")).get("etfs", {}).get("rows", [])]
    import re as _re
    EXTRA += _re.findall(r'\("([A-Z]{2,5})", "', (root / "scripts" / "etfs.py").read_text(encoding="utf-8").split("ETFS = [")[1].split("]")[0])
except Exception as e: print("extra list", type(e).__name__, e, flush=True)
EXTRA = sorted(set(EXTRA) - set(uni))
ny = dt.datetime.now(ZoneInfo("America/New_York"))
open_today = ny.strftime("%Y-%m-%d") if ny.weekday() < 5 and ny.hour * 60 + ny.minute < 16 * 60 + 10 else None   # today's session is not finished yet

out = {}
def take(t, df):
    try:
        df = df.dropna(subset=["Open", "High", "Low", "Close"])
        if len(df) and open_today and df.index[-1].strftime("%Y-%m-%d") == open_today: df = df.iloc[:-1]
        if len(df) < 30: return
        r = lambda c: [round(float(x), 2) for x in df[c]]
        out[t] = {"d": [d.strftime("%Y-%m-%d") for d in df.index], "o": r("Open"), "h": r("High"), "l": r("Low"), "c": r("Close"), "v": [int(x) for x in df["Volume"].fillna(0)]}
    except Exception as e:
        print(t, "skipped", type(e).__name__, flush=True)

chunks = [uni[i:i + 150] for i in range(0, len(uni), 150)] + [EXTRA]   # the extras in their own batch (crypto trades on weekends too)
for i, chunk in enumerate(chunks):
    if not chunk: continue
    for k in range(2):
        try:
            px = yf.download(chunk, period="3y", interval="1d", auto_adjust=False, group_by="ticker", threads=True, progress=False)
            got = set(px.columns.get_level_values(0))
            for t in chunk:
                if t in got: take(t, px[t])
            break
        except Exception as e:
            print("batch", i, "failed", type(e).__name__, str(e)[:120], flush=True); time.sleep(10)
print("ohlc:", len(out), "of", len(uni), "stocks +", len(EXTRA), "ETFs / crypto", flush=True)
if not out: raise SystemExit("nothing downloaded, the ohlc branch stays as it is")

with tempfile.TemporaryDirectory() as d:
    tp = pathlib.Path(d) / "w"
    g = lambda *a, cwd=None, check=True: subprocess.run(["git", "-c", "user.name=wallstreet-bot", "-c", "user.email=bot@users.noreply.github.com", *a], cwd=cwd or tp, check=check, capture_output=True)
    old = subprocess.run(["git", "clone", "-q", "--depth", "1", "--branch", "ohlc", URL, str(tp)], capture_output=True)   # previous files (kept for stocks that failed now)
    if old.returncode != 0: tp.mkdir(parents=True, exist_ok=True)
    else: subprocess.run(["rm", "-rf", str(tp / ".git")])
    keep = set(uni) | set(EXTRA) | {"_meta"}
    for f in tp.glob("*.json"):
        if f.stem not in keep: f.unlink()          # left the site
    for t, j in out.items(): (tp / f"{t}.json").write_text(json.dumps(j, separators=(",", ":")), encoding="utf-8")
    last = max((j["d"][-1] for t, j in out.items() if t in keep and not t.endswith("-USD")), default="")   # crypto also has weekend rows
    (tp / "_meta.json").write_text(json.dumps({"asOf": last, "n": len(list(tp.glob('*.json')))}), encoding="utf-8")
    g("init", "-q"); g("checkout", "-q", "--orphan", "ohlc"); g("add", "-A"); g("commit", "-qm", "daily OHLC for the candlestick chart")
    g("push", "-fq", URL, "ohlc")
print("ohlc published, last session", last, flush=True)
