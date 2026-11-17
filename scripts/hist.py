"""Our own daily close history (split-adjusted), built from Massive (Polygon) grouped-daily bars.
Stored as close.csv.gz (rows = dates, columns = tickers) on the `history` branch, force-pushed as one commit
so it never grows the main history. Needs MASSIVE_KEY (free tier: 5 calls/min, previous sessions only).

load()            -> DataFrame (may be empty)
update(df, keep)  -> appends missing sessions + applies new splits; returns (df, report)
save(df)          -> pushes to the history branch (needs GH_TOKEN or a git remote with push rights)
"""
import io, json, os, gzip, subprocess, tempfile, time, pathlib, urllib.request, datetime as dt
import pandas as pd

KEY = os.environ.get("MASSIVE_KEY", "").strip()
REPO = os.environ.get("GITHUB_REPOSITORY", "sagirozio/wallstreet-he")
ROOT = pathlib.Path(__file__).resolve().parent.parent
_last = [0.0]

def _get(url):
    wait = 12.5 - (time.time() - _last[0])          # 5 calls / minute
    if wait > 0: time.sleep(wait)
    for k in range(4):
        _last[0] = time.time()
        try:
            with urllib.request.urlopen(url, timeout=90) as r: return json.loads(r.read().decode())
        except Exception as e:
            msg = str(e)
            if "403" in msg or "NOT_AUTHORIZED" in msg: return {"_denied": True}
            time.sleep(15 * (k + 1))
    return {}

def grouped(day):
    j = _get(f"https://api.massive.com/v2/aggs/grouped/locale/us/market/stocks/{day:%Y-%m-%d}?adjusted=true&apiKey={KEY}")
    if j.get("_denied"): return None                 # not available yet on the free plan (today / future)
    return {x["T"].replace(".", "-"): float(x["c"]) for x in j.get("results", []) or [] if x.get("c")}

def splits_since(day):
    j = _get(f"https://api.massive.com/v3/reference/splits?execution_date.gte={day:%Y-%m-%d}&limit=1000&apiKey={KEY}")
    return j.get("results", []) or []

def load():
    try:
        subprocess.run(["git", "fetch", "-q", "--depth", "1", "origin", "history"], cwd=ROOT, check=True, capture_output=True)
        raw = subprocess.run(["git", "show", "origin/history:close.csv.gz"], cwd=ROOT, check=True, capture_output=True).stdout
        df = pd.read_csv(io.BytesIO(gzip.decompress(raw)), index_col=0, parse_dates=True)
        print("history loaded", df.shape, df.index[-1].date() if len(df) else None, flush=True)
        return df
    except Exception as e:
        print("no history yet", type(e).__name__, flush=True)
        return pd.DataFrame()

def update(df, keep, start=None):
    """Append every session after the last stored one (up to yesterday, New York) and apply splits."""
    rep = {"added": [], "splits": 0}
    if not KEY: return df, rep
    ny_today = pd.Timestamp.now(tz="America/New_York").normalize().tz_localize(None)
    d = (df.index[-1] + pd.Timedelta(days=1)) if len(df) else (start or ny_today - pd.Timedelta(days=430))
    since = d
    rows = {}
    while d < ny_today:
        if d.weekday() < 5:
            g = grouped(d)
            if g is None: break
            if g: rows[d] = {t: g[t] for t in keep if t in g}; rep["added"].append(str(d.date()))
        d += pd.Timedelta(days=1)
    if rows:
        new = pd.DataFrame.from_dict(rows, orient="index")
        df = pd.concat([df, new]).sort_index()
        df = df[~df.index.duplicated(keep="last")]
    if len(df) and len(rows) and since is not None:
        for s in splits_since(since - pd.Timedelta(days=1)):
            t = (s.get("ticker") or "").replace(".", "-"); ex = pd.Timestamp(s.get("execution_date"))
            f, to = s.get("split_from"), s.get("split_to")
            if t in df.columns and f and to:
                df.loc[df.index < ex, t] = df.loc[df.index < ex, t] * (f / to); rep["splits"] += 1
    return df, rep

def save(df):
    tok = os.environ.get("GH_TOKEN", "")
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as z: z.write(df.round(4).to_csv().encode())
    with tempfile.TemporaryDirectory() as tmp:
        (pathlib.Path(tmp) / "close.csv.gz").write_bytes(buf.getvalue())
        run = lambda *a: subprocess.run(["git", *a], cwd=tmp, check=True, capture_output=True)
        run("init", "-q"); run("checkout", "-q", "--orphan", "history")
        c = ["-c", "user.name=wallstreet-bot", "-c", "user.email=bot@users.noreply.github.com"]
        run(*c, "add", "close.csv.gz"); run(*c, "commit", "-qm", "daily close history")
        url = f"https://x-access-token:{tok}@github.com/{REPO}.git" if tok else str(ROOT)
        run("push", "-fq", url, "history")
    print("history saved", df.shape, flush=True)
