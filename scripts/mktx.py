"""Extra research data for the market page, from our own close history (history branch) -> data.json["themes"]["x"]:
  ind[<industry>] = {sp: weekly points of an equal-weight index since the start of the year (start = 100), rk: places gained (+) or lost (-)
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
_prev_year = df.index[df.index.year < df.index[-1].year]
_YTD0 = df.index.get_loc(_prev_year[-1]) if len(_prev_year) else 0
def spark(cols):               # equal-weight index, year to date (from the last close of the previous year), weekly points
    w = df[cols].iloc[_YTD0:]
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
    wy = df.loc[prev[-1]:] if len(prev) else df[df.index.year == year]   # year to date (from the last close of last year)
    i0 = df.index.get_loc(wy.index[0]); p0 = max(0, i0 - 199)            # + up to 199 sessions before it, for the 50/200-day averages
    w = df.iloc[p0:]; y0 = i0 - p0
    uni = {s[0] for l in stocks.values() for s in l}
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN"); repo = os.environ.get("GITHUB_REPOSITORY", "sagirozio/wallstreet-he")
    url = f"https://x-access-token:{token}@github.com/{repo}.git" if token else subprocess.run(["git", "remote", "get-url", "origin"], cwd=root, capture_output=True, text=True).stdout.strip()
    with tempfile.TemporaryDirectory() as t:
        tp = pathlib.Path(t); n = 0
        # dates/arrays start y0 sessions before the year: the page shows from y0 on and uses the earlier ones only for the averages
        (tp / "_dates.json").write_text(json.dumps({"asOf": str(w.index[-1].date()), "y0": y0, "dates": [str(d.date()) for d in w.index]}, separators=(",", ":")))
        for tk in w.columns:
            if tk not in uni: continue
            c = w[tk]
            if pd.isna(c.iloc[-1]) or c.notna().sum() < 5: continue
            (tp / f"{tk}.json").write_text(json.dumps([None if pd.isna(v) else (round(float(v), 2) if v < 1000 else round(float(v), 1)) for v in c], separators=(",", ":")))
            n += 1
        # _spark.json: one small year-to-date line per stock for the tables (every 5th session + the last one, scaled to 0-99)
        w = wy   # the table sparklines stay year to date
        idx = list(range(0, len(w), 5)); idx = idx if idx[-1] == len(w) - 1 else idx + [len(w) - 1]
        sp = {}
        for tk in w.columns:
            if tk not in uni: continue
            c = w[tk].iloc[idx]
            if pd.isna(c.iloc[-1]) or c.notna().sum() < 4: continue
            lo, hi = float(c.min()), float(c.max())
            sp[tk] = [None if pd.isna(v) else (round((float(v) - lo) / (hi - lo) * 99) if hi > lo else 50) for v in c]
        (tp / "_spark.json").write_text(json.dumps({"asOf": str(w.index[-1].date()), "d": sp}, separators=(",", ":")))
        g = lambda *a: subprocess.run(["git", "-c", "user.name=wallstreet-bot", "-c", "user.email=bot@users.noreply.github.com", *a], cwd=t, check=True, capture_output=True)
        g("init", "-q"); g("checkout", "-q", "--orphan", "px"); g("add", "-A"); g("commit", "-qm", "year-to-date price lines")
        g("push", "-fq", url, "px")
    print("px published", n, "stocks,", len(w), "sessions year to date, +", y0, "before")
try: publish_px()
except Exception as e: print("px publish failed", type(e).__name__, str(e)[:200])

# ---------- leaders (stocks page "מובילים") ----------
# rsl: stocks whose RS line (close / SPY) is at a 52-week high today -> [T, % below the 52-week price high]
#      (a price still below its high = the RS line led the price)
# newl: stocks whose RS rating crossed 90 in the last 5 sessions -> [T, rating 5 sessions ago]
try:
    uni = [s_[0] for l_ in stocks.values() for s_ in l_ if s_[0] in df.columns]
    lead = {}
    if "SPY" in df.columns and len(df) >= 253:
        w = df.iloc[-252:]
        rl = w[uni].div(w["SPY"], axis=0)
        ok = rl.iloc[-1].notna() & (rl.notna().sum() >= 240)
        top = rl.loc[:, ok]
        hit = top.columns[(top.iloc[-1] >= top.max() * 0.999)]
        off = (w[hit].iloc[-1] / w[hit].max() - 1) * 100
        lead["rsl"] = sorted([[t_, round(float(off[t_]), 1)] for t_ in hit if pd.notna(off[t_])], key=lambda x: x[1])
    mem = {t_ for l_ in ((data.get("sectors") or {}).get("mem") or {}).values() for t_ in l_}
    def rs_at(back):   # IBD-style weighted 12-month score at `back` sessions ago, as a 1-99 percentile against the S&P 500 stocks
        i = len(df) - 1 - back
        if i < 252: return {}
        c = df.iloc[i]
        r = lambda n: c / df.iloc[i - n] - 1
        q, h, y = r(63), r(126), r(252)
        sc = (0.4 * q + 0.2 * h + 0.2 * (h + y) / 2 + 0.2 * y).dropna()
        ref = sc[[t_ for t_ in sc.index if t_ in mem]].sort_values()
        if len(ref) < 100: return {}
        import numpy as np
        pos = np.searchsorted(ref.values, sc.values, side="left")
        return {t_: max(1, min(99, round(p_ / len(ref) * 99))) for t_, p_ in zip(sc.index, pos)}
    now_rs, old_rs = rs_at(0), rs_at(5)
    if now_rs and old_rs:
        lead["newl"] = sorted([[t_, old_rs[t_]] for t_ in uni if now_rs.get(t_, 0) >= 90 and t_ in old_rs and old_rs[t_] < 90], key=lambda x: -now_rs[x[0]])
        # left the 90+ group this week -> [T, rating 5 sessions ago, rating now]
        lead["outl"] = sorted([[t_, old_rs[t_], now_rs[t_]] for t_ in uni if old_rs.get(t_, 0) >= 90 and t_ in now_rs and now_rs[t_] < 90], key=lambda x: x[2])
    # RS line first reached a 52-week high in the last 5 sessions (not already at one 5 sessions ago)
    if "SPY" in df.columns and len(df) >= 258 and lead.get("rsl") is not None:
        w5 = df.iloc[-257:-5]; r5 = w5[uni].div(w5["SPY"], axis=0)
        was = set(r5.columns[(r5.iloc[-1] >= r5.max() * 0.999)])
        lead["rslNew"] = [t_ for t_, _ in lead["rsl"] if t_ not in was]
    # sectors: RS rating of each sector ETF now and 4 weeks (20 sessions) ago, same scale as the stocks -> rot[ETF] = [now, 4 weeks ago]
    etfs = [e for e in ("XLK", "XLC", "XLY", "XLP", "XLE", "XLF", "XLV", "XLI", "XLRE", "XLB", "XLU") if e in df.columns]
    def rs_of(cols, back):
        i = len(df) - 1 - back
        if i < 252: return {}
        c = df.iloc[i]; r = lambda n: c / df.iloc[i - n] - 1
        q, h, y = r(63), r(126), r(252)
        sc = (0.4 * q + 0.2 * h + 0.2 * (h + y) / 2 + 0.2 * y)
        ref = sc[[t_ for t_ in sc.index if t_ in mem]].dropna().sort_values()
        if len(ref) < 100: return {}
        import numpy as np
        # the same scale for other symbols (etfs.py rates the thematic ETFs with it): 199 evenly spaced scores of the S&P 500 stocks, sorted
        if back == 0: X["rsq"] = [round(float(v), 4) for v in ref.values[np.linspace(0, len(ref) - 1, 199).astype(int)]]
        return {e: max(1, min(99, round(int(np.searchsorted(ref.values, sc[e], side="left")) / len(ref) * 99))) for e in cols if pd.notna(sc.get(e))}
    a0, a20 = rs_of(etfs, 0), rs_of(etfs, 20)
    if a0: X["rot"] = {e: [a0[e], a20.get(e)] for e in a0}
    lead["asOf"] = str(df.index[-1].date())
    X["lead"] = lead
    print("leaders: RS-line highs", len(lead.get("rsl", [])), "new RS 90+", len(lead.get("newl", [])))
except Exception as e:
    print("leaders failed", type(e).__name__, e)
T["x"] = X; data["themes"] = T
p.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
print("mktx", X["asOf"], "industries", len(X["ind"]), "ranked", len(rn), "sectors", len(X["sec"]), "top5", X["top5"])
