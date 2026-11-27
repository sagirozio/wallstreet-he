"""Market-leadership lists for the research page (#mlead). Facts only: each list is a plain, stated screen on price,
volume and reported sales. Nothing here is a signal or a recommendation.

Input: the daily candles that ohlc.py has just downloaded ({ticker: {"d","o","h","l","c","v"}}), stocks.json (names,
industries), data.json (S&P 500 members, for the RS rating), earndates.json (report dates) and s/<T>.json (sales growth).
Output: leaders.json = {"asOf": last session, "L": {list id: rows}}.

Run by ohlc.py after its download; `python scripts/leaders.py <dir of ohlc files>` runs it on saved files.

The lists
  hold   stocks that fell least (or rose) while the S&P 500 dropped 5% or more from a high: the current drop, else the last one
  rsline RS line (close / SPY close) at a 52-week high while the price is still 3% or more below its own 52-week high
  groups industries with the most stocks at a new 52-week high in the last 5 sessions
  climb  RS rating up 15 points or more in 20 sessions, now 70 or higher
  gap    up 8% or more on 1.5x average volume right after a report (last 90 days), and no close below that day's low since
  ind    the stock with the highest RS rating in each industry
  accel  sales growth (year over year) higher in each of the last 3 quarters, RS 80 or higher
  accum  last 25 sessions: up days on above-average volume minus down days on above-average volume
  quiet  within 5% of the 52-week high, with a narrower daily range and lower volume in the last 10 sessions than in the last 50
"""
import bisect, datetime as dt, json, pathlib, sys

root = pathlib.Path(__file__).resolve().parent.parent
TOP = 30


def _load(name, default):
    try: return json.loads((root / name).read_text(encoding="utf-8"))
    except Exception: return default


def _rs_score(c, i):
    """The site's RS score at bar i: 0.4*3M + 0.2*6M + 0.2*9M + 0.2*12M (9M = the 6M / 12M average), as in build.py."""
    if i < 252 or c[i - 252] <= 0 or c[i - 126] <= 0 or c[i - 63] <= 0: return None
    q = (c[i] / c[i - 63] - 1) * 100; h = (c[i] / c[i - 126] - 1) * 100; y = (c[i] / c[i - 252] - 1) * 100
    return 0.4 * q + 0.2 * h + 0.2 * (h + y) / 2 + 0.2 * y


def build(C):
    stocks = _load("stocks.json", {}).get("stocks", {})
    ind_of = {s[0]: ind for ind, lst in stocks.items() for s in lst}
    uni = [t for t in ind_of if t in C and len(C[t]["c"]) >= 60]
    spx_mem = {t for l in ((_load("data.json", {}).get("sectors") or {}).get("mem") or {}).values() for t in l}
    ref = C.get("SPX") or C.get("SPY")
    spy = C.get("SPY") or ref
    if not ref or not uni: return None
    last = ref["d"][-1]
    # only stocks whose last bar is the last session (a halted or stale file would skew every list)
    uni = [t for t in uni if C[t]["d"][-1] == last]

    # ---- RS rating now and 20 sessions ago, against the S&P 500 stocks ----
    def ratings(back):
        sc = {}
        for t in uni:
            c = C[t]["c"]; i = len(c) - 1 - back
            s = _rs_score(c, i) if i >= 0 else None
            if s is not None: sc[t] = s
        base = sorted(v for t, v in sc.items() if t in spx_mem)
        if len(base) < 100: base = sorted(sc.values())
        if len(base) < 100: return {}
        return {t: max(1, min(99, round(bisect.bisect_left(base, v) / len(base) * 99))) for t, v in sc.items()}
    RS, RS0 = ratings(0), ratings(20)

    hi52 = {}; dist = {}
    for t in uni:
        h = C[t]["h"][-252:]; m = max(h); hi52[t] = m; dist[t] = round((C[t]["c"][-1] / m - 1) * 100, 1) if m > 0 else None
    r1 = lambda x: None if x is None else round(x, 1)
    L = {}

    # ---- hold: the S&P 500's drop of 5%+ from a high (current, else the last one within 2 years) ----
    rc, rd = ref["c"][-504:], ref["d"][-504:]
    peak_i = 0; dd = []
    for i, v in enumerate(rc):
        if v >= rc[peak_i]: peak_i = i
        dd.append((v / rc[peak_i] - 1, peak_i))
    hold = None
    if dd and dd[-1][0] <= -0.05:
        hold = (dd[-1][1], len(rc) - 1, 1)
    else:
        idx = [i for i, (x, _) in enumerate(dd) if x <= -0.05]
        if idx:
            p = dd[idx[-1]][1]
            end = next((i for i in range(p + 1, len(rc)) if rc[i] >= rc[p]), len(rc) - 1)   # the day the index was back at the high
            tr = min(range(p, end + 1), key=lambda i: rc[i])
            hold = (p, tr, 0)
    if hold:
        d0, d1 = rd[hold[0]], rd[hold[1]]; rows = []
        for t in uni:
            D = C[t]["d"]; a = bisect.bisect_left(D, d0); b = bisect.bisect_left(D, d1)
            if a < len(D) and b < len(D) and D[a] == d0 and D[b] == d1 and C[t]["c"][a] > 0:
                rows.append([t, round((C[t]["c"][b] / C[t]["c"][a] - 1) * 100, 1), RS.get(t), dist[t]])
        rows.sort(key=lambda r: -r[1])
        L["hold"] = {"from": d0, "to": d1, "now": hold[2], "spx": round((rc[hold[1]] / rc[hold[0]] - 1) * 100, 1), "rows": rows[:TOP]}

    # ---- rsline: the RS line is at a 52-week high before the price ----
    sd = {d: v for d, v in zip(spy["d"], spy["c"])}; rows = []
    for t in uni:
        D, c = C[t]["d"][-252:], C[t]["c"][-252:]
        if len(c) < 200: continue
        rl = [x / sd[d] for d, x in zip(D, c) if sd.get(d)]
        if len(rl) < 200 or dist[t] is None: continue
        if rl[-1] >= max(rl) * 0.995 and dist[t] <= -3: rows.append([t, RS.get(t), dist[t]])
    rows.sort(key=lambda r: (-(r[1] or 0), -r[2]))
    L["rsline"] = rows[:TOP]

    # ---- groups: new 52-week highs in the last 5 sessions, by industry ----
    newhi = set()
    for t in uni:
        h = C[t]["h"]
        if len(h) >= 200 and max(h[-5:]) >= max(h[-252:-5]): newhi.add(t)
    g = []
    for ind, lst in stocks.items():
        mem = [s[0] for s in lst if s[0] in hi52]; hit = sorted((t for t in mem if t in newhi), key=lambda t: -(RS.get(t) or 0))
        if len(hit) >= 2 and len(mem) >= 4: g.append([ind, len(hit), len(mem), hit[:12]])
    g.sort(key=lambda r: (-r[1], -r[1] / r[2]))
    L["groups"] = g[:15]

    # ---- climb: the RS rating rose 15 points or more in 20 sessions ----
    rows = [[t, RS0[t], RS[t], dist[t]] for t in uni if t in RS and t in RS0 and RS[t] >= 70 and RS[t] - RS0[t] >= 15]
    rows.sort(key=lambda r: (-(r[2] - r[1]), -r[2]))
    L["climb"] = rows[:TOP]

    # ---- gap: a jump on a report that has held ----
    ed = (_load("earndates.json", {}).get("d") or {}); lim = (dt.date.fromisoformat(last) - dt.timedelta(days=90)).isoformat(); rows = []
    for t in uni:
        D, c, l, v = C[t]["d"], C[t]["c"], C[t]["l"], C[t]["v"]
        for rep in ed.get(t) or []:
            if not (lim <= rep <= last): continue
            i0 = bisect.bisect_left(D, rep); best = None
            for i in (i0, i0 + 1):                       # the report day, or the next session (reports after the close)
                if 51 <= i < len(D) and c[i - 1] > 0:
                    ch = (c[i] / c[i - 1] - 1) * 100
                    if best is None or ch > best[1]: best = (i, ch)
            if not best or best[1] < 8: continue
            i = best[0]; av = sum(v[i - 50:i]) / 50
            if av <= 0 or v[i] < 1.5 * av: continue
            if i + 1 < len(c) and min(c[i + 1:]) < l[i]: continue
            rows.append([t, D[i], round(best[1], 1), round(v[i] / av, 1), round((c[-1] / c[i] - 1) * 100, 1), RS.get(t)]); break
    rows.sort(key=lambda r: (r[1], r[2]), reverse=True)
    L["gap"] = rows[:TOP]

    # ---- sales growth by quarter (newest first), from the stock files ----
    def sales(t):
        try: eh = json.loads((root / "s" / f"{t}.json").read_text(encoding="utf-8")).get("eh") or []
        except Exception: return []
        return [q.get("ry") for q in eh[:4]]

    # ---- ind: the highest RS rating in each industry ----
    rows = []
    for ind, lst in stocks.items():
        mem = [s[0] for s in lst if s[0] in RS]
        if len(mem) < 4: continue
        t = max(mem, key=lambda x: (RS[x], dist[x] or -999)); sg = sales(t)
        rows.append([ind, t, RS[t], dist[t], sg[0] if sg else None, len(mem)])
    rows.sort(key=lambda r: (-r[2], -(r[3] or -999)))
    L["ind"] = rows[:40]

    # ---- accel: sales growth higher in each of the last 3 quarters, RS 80+ ----
    rows = []
    for t in uni:
        if RS.get(t, 0) < 80: continue
        sg = sales(t)
        if len(sg) == 4 and all(x is not None for x in sg) and sg[0] > sg[1] > sg[2] > sg[3]: rows.append([t, RS[t], sg[::-1], dist[t]])
    rows.sort(key=lambda r: -r[2][-1])
    L["accel"] = rows[:TOP]

    # ---- accum: up days on above-average volume minus down days on above-average volume, last 25 sessions ----
    rows = []
    for t in uni:
        c, v = C[t]["c"], C[t]["v"]; n = len(c)
        if n < 80: continue
        up = dn = 0
        for i in range(n - 25, n):
            av = sum(v[i - 50:i]) / 50
            if av > 0 and v[i] > av:
                if c[i] > c[i - 1]: up += 1
                elif c[i] < c[i - 1]: dn += 1
        if up - dn >= 4: rows.append([t, up, dn, RS.get(t), dist[t]])
    rows.sort(key=lambda r: (-(r[1] - r[2]), -(r[3] or 0)))
    L["accum"] = rows[:TOP]

    # ---- quiet: near the high, with a narrower range and lower volume ----
    rows = []
    for t in uni:
        h, l, c, v = C[t]["h"], C[t]["l"], C[t]["c"], C[t]["v"]; n = len(c)
        if n < 80 or dist[t] is None or dist[t] < -5: continue
        rng = [(h[i] - l[i]) / c[i] for i in range(n - 50, n) if c[i] > 0]
        if len(rng) < 50: continue
        a10, a50 = sum(rng[-10:]) / 10, sum(rng) / 50; v10, v50 = sum(v[-10:]) / 10, sum(v[-50:]) / 50
        if a50 > 0 and v50 > 0 and a10 <= 0.75 * a50 and v10 < v50: rows.append([t, round(a10 / a50 * 100), round(v10 / v50 * 100), RS.get(t), dist[t]])
    rows.sort(key=lambda r: r[1])
    L["quiet"] = rows[:TOP]

    return {"asOf": last, "n": len(uni), "L": L}


def write(C):
    try:
        out = build(C)
        if not out: print("leaders: no data", flush=True); return
        (root / "leaders.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print("leaders:", out["asOf"], {k: (len(v["rows"]) if isinstance(v, dict) else len(v)) for k, v in out["L"].items()}, flush=True)
    except Exception as e:
        print("leaders failed", type(e).__name__, str(e)[:200], flush=True)


if __name__ == "__main__":
    d = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if not d or not d.is_dir(): raise SystemExit("usage: leaders.py <dir with the ohlc files>")
    C = {}
    for f in d.glob("*.json"):
        if f.stem.startswith("_"): continue
        try: C[f.stem] = json.loads(f.read_text(encoding="utf-8"))
        except Exception: pass
    write(C)
