"""Fill earnings cards from our SEC EDGAR quarterly files (fund/<T>.json, built weekly by fundamentals.py; no network):
- revYoy: card revenue vs the same quarter a year earlier (official 10-Q / 10-K numbers)
- revAct: when the card has none and SEC already has the quarter
- epsYoy: only from our own card of the same quarter last year (both adjusted EPS; SEC EPS is GAAP, not comparable)."""
import json, pathlib, datetime as dt
root = pathlib.Path(__file__).resolve().parent.parent
p = root / "data.json"; d = json.loads(p.read_text(encoding="utf-8"))
D = lambda s: dt.date.fromisoformat(str(s)[:10])
F = {}
def fund(t):
    if t not in F:
        f = root / "fund" / f"{t}.json"
        F[t] = json.loads(f.read_text()) if f.exists() else None
    return F[t]
def q_in(f, lo, hi):
    best = None
    for i, q in enumerate(f["q"]):
        if lo <= D(q) <= hi and f["rev"][i]: best = i
    return best
by_t = {}
for r in d["reports"]: by_t.setdefault(r["t"], []).append(r)
n_rev = n_act = n_eps = 0
for r in d["reports"]:
    if r.get("revCur"): continue
    day = D(r["date"]); f = fund(r["t"])
    if f and f.get("rev"):
        cur = q_in(f, day - dt.timedelta(days=80), day - dt.timedelta(days=3))
        if r.get("revAct") is None and cur is not None:
            r["revAct"] = round(f["rev"][cur] / 1e9, 4); n_act += 1
        if r.get("revYoy") is None and r.get("revAct"):
            prev = q_in(f, day - dt.timedelta(days=365 + 80), day - dt.timedelta(days=365 - 20))
            if prev is not None and (cur is None or prev != cur):
                y = round((r["revAct"] * 1e9 / f["rev"][prev] - 1) * 100, 1)
                if -90 < y < 400: r["revYoy"] = y; n_rev += 1
    if r.get("epsYoy") is None and r.get("epsAct") is not None:
        old = [o for o in by_t[r["t"]] if o is not r and 330 <= (day - D(o["date"])).days <= 400 and o.get("epsAct")]
        if old and old[0]["epsAct"] > 0:
            r["epsYoy"] = round((r["epsAct"] / old[0]["epsAct"] - 1) * 100, 1); n_eps += 1
# sanity on automatic cards: drop exact duplicates, and estimates that clearly don't match the reported basis
seen, keep, n_dup, n_bad = set(), [], 0, 0
for r in d["reports"]:
    if r["id"] in seen and r.get("auto"): n_dup += 1; continue
    seen.add(r["id"]); keep.append(r)
    if not r.get("auto"): continue
    a, e = r.get("epsAct"), r.get("epsEst")
    if a is not None and e is not None and (abs(a - e) > max(1.0, 3 * abs(e)) and abs(e) > 0 or (e == 0 and abs(a) > 0.5)):
        r["epsEst"] = None; r["epsNote"] = "basis"; n_bad += 1     # e.g. GAAP actual vs adjusted estimate
    a, e = r.get("revAct"), r.get("revEst")
    if a and e and not (0.5 < a / e < 2): r["revEst"] = None; n_bad += 1
    if r.get("revYoy") is not None and abs(r["revYoy"]) > 1000: r["revYoy"] = None; n_bad += 1
d["reports"] = keep
print("sanity: duplicates dropped", n_dup, "implausible estimates cleared", n_bad)
p.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
print("SEC fill: revYoy", n_rev, "revAct", n_act, "epsYoy (from last year's card)", n_eps)
