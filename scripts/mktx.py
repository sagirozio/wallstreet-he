"""Extra research data for the market page, from our own close history (history branch) -> data.json["themes"]["x"]:
  ind[<industry>] = {sp: 13 weekly points of an equal-weight index over the last 3 months (start = 100), rk: places gained (+) or lost (-)
                     in the 1-month ranking vs 5 sessions ago}
  sec[<sector>]   = {sp: same sparkline for the sector, a50: % of its stocks above their 50-day average, c50: how many, n: stocks counted}
  (ind[...] has the same n / c50 / a50)
  top5            = {in: industries that entered the top 5 (1-month ranking) in the last 5 sessions, out: those that left}
Only groups with 3+ stocks are ranked (like the table). Runs after themes.py in the nightly update."""
import json, pathlib, sys
import pandas as pd
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import hist as H

root = pathlib.Path(__file__).resolve().parent.parent
p = root / "data.json"
data = json.loads(p.read_text(encoding="utf-8"))
T = data.get("themes") or {}
df = H.load()
if df.empty or len(df) < 90: raise SystemExit("no history")
df = df.sort_index().ffill(limit=3)
stocks, ind_sec = T.get("stocks") or {}, T.get("indSector") or {}

def month_ret(cols, back):     # equal-weight 1-month (21 sessions) return of the group, as of `back` sessions ago
    a, b = df[cols].iloc[-1 - back], df[cols].iloc[-1 - back - 21]
    r = (a / b - 1).dropna()
    r = r[(r > -0.95) & (r < 9)]
    return float(r.mean() * 100) if len(r) else None
def spark(cols):               # equal-weight index, 3 months, weekly points
    w = df[cols].iloc[-64:]
    w = w.loc[:, w.iloc[0].notna() & w.iloc[-1].notna()]
    if w.shape[1] == 0: return None
    idx = (w / w.iloc[0]).mean(axis=1) * 100
    pts = idx.iloc[::-1].iloc[::5].iloc[::-1]
    return [round(float(v), 1) for v in pts]

X = {"ind": {}, "sec": {}, "asOf": str(df.index[-1].date())}
now, old, sec_cols = {}, {}, {}
for ind, lst in stocks.items():
    cols = [s[0] for s in lst if s[0] in df.columns]
    if ind_sec.get(ind): sec_cols.setdefault(ind_sec[ind], []).extend(cols)
    if not cols: continue
    sp = spark(cols)
    if sp: X["ind"][ind] = {"sp": sp}
    if len(lst) >= 3:
        a, b = month_ret(cols, 0), month_ret(cols, 5)
        if a is not None and b is not None: now[ind], old[ind] = a, b
rank = lambda d: {k: i + 1 for i, (k, _) in enumerate(sorted(d.items(), key=lambda x: -x[1]))}
rn, ro = rank(now), rank(old)
for ind in rn:
    X["ind"].setdefault(ind, {})["rk"] = ro[ind] - rn[ind]
# top 5 as shown in the table (themes rows, 1 month) vs the top 5 of 5 sessions ago
rows = [r for r in T.get("rows", []) if len(stocks.get(r.get("en"), [])) >= 3 and r.get("m") is not None]
top_now = [r["en"] for r in sorted(rows, key=lambda r: -r["m"])[:5]]
top_old = [k for k, v in sorted(ro.items(), key=lambda x: x[1])[:5]]
X["top5"] = {"in": [k for k in top_now if k not in top_old], "out": [k for k in top_old if k not in top_now]}
ma50 = df.iloc[-50:].mean()
def above50(cols):             # stocks above their 50-day average: {n: counted, c50: how many above, a50: %}
    last = df[cols].iloc[-1]
    ok = last.notna() & ma50[cols].notna() & df[cols].iloc[-50].notna()
    n = int(ok.sum())
    if not n: return {"n": 0}
    c = int((last[ok] > ma50[cols][ok]).sum())
    return {"n": n, "c50": c, "a50": round(c / n * 100)}
for ind, lst in stocks.items():
    cols = [s[0] for s in lst if s[0] in df.columns]
    if cols: X["ind"].setdefault(ind, {}).update(above50(cols))
for sec, cols in sec_cols.items():
    cols = sorted(set(cols))
    x = above50(cols)
    sp = spark(cols)
    if sp: x["sp"] = sp
    X["sec"][sec] = x
# ---------- year-to-date daily price line for every stock page -> `px` branch (orphan, force-pushed: no churn on main) ----------
# px/_dates.json = {asOf, dates: [...]} from the last close of the previous year; px/<T>.json = [close, ...] aligned to the dates
def publish_px():
    import os, subprocess, tempfile
    year = df.index[-1].year
    prev = df.index[df.index.year < year]
    w = df.loc[prev[-1]:] if len(prev) else df[df.index.year == year]
    uni = {s[0] for l in stocks.values() for s in l}
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN"); repo = os.environ.get("GITHUB_REPOSITORY", "sagirozio/wallstreet-he")
    url = f"https://x-access-token:{token}@github.com/{repo}.git" if token else subprocess.run(["git", "remote", "get-url", "origin"], cwd=root, capture_output=True, text=True).stdout.strip()
    with tempfile.TemporaryDirectory() as t:
        tp = pathlib.Path(t); n = 0
        (tp / "_dates.json").write_text(json.dumps({"asOf": str(w.index[-1].date()), "dates": [str(d.date()) for d in w.index]}, separators=(",", ":")))
        for tk in w.columns:
            if tk not in uni: continue
            c = w[tk]
            if pd.isna(c.iloc[-1]) or c.notna().sum() < 5: continue
            (tp / f"{tk}.json").write_text(json.dumps([None if pd.isna(v) else (round(float(v), 2) if v < 1000 else round(float(v), 1)) for v in c], separators=(",", ":")))
            n += 1
        g = lambda *a: subprocess.run(["git", "-c", "user.name=wallstreet-bot", "-c", "user.email=bot@users.noreply.github.com", *a], cwd=t, check=True, capture_output=True)
        g("init", "-q"); g("checkout", "-q", "--orphan", "px"); g("add", "-A"); g("commit", "-qm", "year-to-date price lines")
        g("push", "-fq", url, "px")
    print("px published", n, "stocks,", len(w), "sessions from", w.index[0].date())
try: publish_px()
except Exception as e: print("px publish failed", type(e).__name__, str(e)[:200])

T["x"] = X; data["themes"] = T
p.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
print("mktx", X["asOf"], "industries", len(X["ind"]), "ranked", len(rn), "sectors", len(X["sec"]), "top5", X["top5"])
