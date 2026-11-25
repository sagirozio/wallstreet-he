"""Backtest of the breakout setup (Kristjan Kullamaggie's stair-step breakouts) on the daily candles of the ohlc branch.

Facts only: what the rules would have done on past data. Not advice, no orders, no broker.

Setup, all from data up to the day before the breakout (no look-ahead):
  scan       the stock is in the top 2% of the universe by 1-month, 3-month or 6-month return,
             RS rating >= 90 (as on the site, against the S&P 500 members) and ADR(20) >= 5%
  1. move    a rise of >= 30% (low to high) within <= 25 sessions, peaking 10-40 sessions ago,
             and no higher high since the peak
  2. base    10-40 sessions since the peak; the pullback from the peak is <= 25%;
             the lowest low of the second half of the base is above the lowest low of the first half;
             the average daily range of the last 5 sessions is below that of the first 5;
             >= 70% of the closes in the base are above the 20-day average
  3. trigger today's high goes over the highest high of the base
Trade
  entry      ORH: from 5-minute bars, the first break of max(opening-range high, base high) + 1 cent
  stop       today's low, but no wider than the stock's ADR (20 sessions). When the ADR cap is above today's low,
             daily data can't tell whether the low came before or after the entry: the stop counts as hit (worst case)
  partial    sell 1/2 at the close of day N (3 or 5), then move the stop to the entry price
  trail      the rest: exit at the first close below the 10- (or 20-) day average
  size       risk 0.5% of equity per trade (entry - stop), at most 25% of equity in one stock, at most 10 positions
  costs      0.1% a side (commission + slippage)
Variants: trail 10 / 20 x partial day 3 / 5 x with / without the breadth filter (> 50% of the universe above its 50-day).
Survivorship bias: the universe is today's stocks (market cap > $1B now), so the past looks better than it was.

Output: lab.enc = the results (summary per variant, equity curves against SPY, trades), encrypted with the LAB_PASS secret.
The page lab.html asks for the passphrase and decrypts in the browser. Minute bars stay in the Actions cache (not in the repo).
Usage: MASSIVE_KEY=... LAB_PASS=... python scripts/lab_backtest.py <ohlc dir> lab.enc
"""
import json, sys, pathlib, math, os
import numpy as np

SRC = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "ohlc")
OUT = pathlib.Path(sys.argv[2] if len(sys.argv) > 2 else "bt.json")
START = sys.argv[3] if len(sys.argv) > 3 else "2023-01-01"
P = dict(top=0.02, move=0.30, move_len=25, base_min=10, base_max=40, pull=0.25, surf=0.70,
         risk=0.005, cap=0.25, rs=90, adr=0.05, orm=5, maxpos=10, cost=0.001, min_px=3.0, min_dv=3e6)

# ---- load: align every stock on SPY's sessions ----
spy = json.loads((SRC / "SPY.json").read_text())
D = spy["d"]; T = len(D); idx = {d: i for i, d in enumerate(D)}
tick, O, H, L, C, V = [], [], [], [], [], []
for f in sorted(SRC.glob("*.json")):
    t = f.stem
    if t in ("SPY",) or t.startswith("_"): continue
    try: j = json.loads(f.read_text())
    except Exception: continue
    if len(j.get("d", [])) < 150: continue
    a = {k: np.full(T, np.nan) for k in "ohlcv"}
    for n, d in enumerate(j["d"]):
        i = idx.get(d)
        if i is None: continue
        for k in "ohlcv": a[k][i] = j[k][n] if j[k][n] is not None else np.nan
    tick.append(t); O.append(a["o"]); H.append(a["h"]); L.append(a["l"]); C.append(a["c"]); V.append(a["v"])
O, H, L, C, V = (np.array(x) for x in (O, H, L, C, V))
N = len(tick); S0 = max(130, next(i for i, d in enumerate(D) if d >= START)); print("start", D[S0]); print("stocks", N, "sessions", T, D[0], D[-1])

def sma(x, n):
    out = np.full_like(x, np.nan); cs = np.nancumsum(np.nan_to_num(x), axis=1); cnt = np.cumsum(~np.isnan(x), axis=1)
    s = cs[:, n:] - cs[:, :-n]; k = cnt[:, n:] - cnt[:, :-n]
    out[:, n:] = np.where(k == n, s / n, np.nan); return out
MA10, MA20, MA50 = sma(C, 10), sma(C, 20), sma(C, 50)
ADR = sma(H / L - 1, 20)                      # fraction
DV = sma(C * V, 20)
def ret(n):
    r = np.full_like(C, np.nan); r[:, n:] = C[:, n:] / C[:, :-n] - 1; return r
R1, R3, R6 = ret(21), ret(63), ret(126)
def topmask(r):
    q = np.nanquantile(r, 1 - P["top"], axis=0); return r >= q
with np.errstate(invalid="ignore"):
    SCAN = topmask(R1) | topmask(R3) | topmask(R6)
    BREADTH = np.nanmean(np.where(np.isnan(MA50), np.nan, (C > MA50).astype(float)), axis=0) * 100
RNG = (H - L) / C
# RS rating (1-99) as on the site: score = 0.4*3M + 0.2*6M + 0.2*9M(avg of 6M,12M) + 0.2*12M, ranked against the S&P 500 members
R12 = ret(252)
SCORE = 0.4 * R3 + 0.2 * R6 + 0.2 * (R6 + R12) / 2 + 0.2 * R12
_dj = sorted({t for v in json.loads(pathlib.Path(os.environ.get("DATA_JSON", "data.json")).read_text())["sectors"]["mem"].values() for t in v})   # S&P 500 members (today's list)
SPXI = np.array([i for i, t in enumerate(tick) if t in set(_dj)])
RS = np.full((N, T), np.nan)
for t in range(T):
    ref = np.sort(SCORE[SPXI, t][~np.isnan(SCORE[SPXI, t])])
    if len(ref) < 100: continue
    RS[:, t] = np.clip(np.round(np.searchsorted(ref, SCORE[:, t]) / len(ref) * 99), 1, 99)
RS[np.isnan(SCORE)] = np.nan
print("spx members found", len(SPXI))

# ---- setups: for each stock and day t, is there a base whose high is the trigger for day t? ----
TRIG = np.full((N, T), np.nan); MOVE = np.full((N, T), np.nan); BLEN = np.zeros((N, T), dtype=np.int16)
for s in range(N):
    h, l, c, ma20 = H[s], L[s], C[s], MA20[s]
    for t in range(130, T):
        y = t - 1                                 # all checks on data up to yesterday
        if not SCAN[s, y] or not (c[y] >= P["min_px"]) or not (DV[s, y] >= P["min_dv"]): continue
        if not (RS[s, y] >= P["rs"]) or not (ADR[s, y] >= P["adr"]): continue
        w0 = t - P["base_max"] - 1; seg = h[w0:t]
        if np.isnan(seg).any(): continue
        p = w0 + int(np.argmax(seg)); blen = y - p
        if blen < P["base_min"] or blen > P["base_max"]: continue
        lo_w = l[p - P["move_len"]:p + 1]
        if np.isnan(lo_w).any(): continue
        mv = h[p] / lo_w.min() - 1
        if mv < P["move"]: continue
        bl, bh, bc, bm = l[p + 1:t], h[p + 1:t], c[p + 1:t], ma20[p + 1:t]
        if bl.min() < h[p] * (1 - P["pull"]): continue
        half = len(bl) // 2
        if not bl[half:].min() > bl[:half].min(): continue
        rg = RNG[s, p + 1:t]
        if not rg[-5:].mean() < rg[:5].mean(): continue
        if np.mean(bc > bm) < P["surf"]: continue
        TRIG[s, t] = bh.max(); MOVE[s, t] = mv; BLEN[s, t] = blen
print("setups", int(np.sum(~np.isnan(TRIG))))

# ---- opening range: 5-minute bars of every breakout day (Massive, cached in minute/) ----
import os, time, urllib.request, urllib.error, datetime as dt
from zoneinfo import ZoneInfo
NY = ZoneInfo("America/New_York"); KEY = os.environ.get("MASSIVE_KEY", ""); MIN = pathlib.Path(os.environ.get("MIN_DIR", "minute")); MIN.mkdir(exist_ok=True)
FIRST = (dt.date.today() - dt.timedelta(days=730)).isoformat()      # the free plan keeps about 2 years of minute bars
S0 = max(S0, next(i for i, d in enumerate(D) if d >= FIRST)); print("minute data from", D[S0])
need = [(s, t) for s, t in zip(*np.where(~np.isnan(TRIG) & (H > TRIG))) if t >= S0]
print("breakout days", len(need))
def bars(s, t):
    f = MIN / f"{tick[s]}_{D[t]}.json"
    if f.exists(): return json.loads(f.read_text())
    if not KEY: return None
    url = f"https://api.massive.com/v2/aggs/ticker/{tick[s]}/range/5/minute/{D[t]}/{D[t]}?adjusted=true&sort=asc&limit=500&apiKey={KEY}"
    for k in range(4):
        try:
            with urllib.request.urlopen(url, timeout=30) as r: j = json.loads(r.read())
            out = [[b["t"], b["o"], b["h"], b["l"], b["c"]] for b in j.get("results") or []]
            f.write_text(json.dumps(out)); time.sleep(float(os.environ.get("MASSIVE_SLEEP", "12.5"))); return out
        except urllib.error.HTTPError as e:
            if e.code == 429: time.sleep(65); continue
            print("http", e.code); time.sleep(12.5); return None
        except Exception as e:
            print("err", type(e).__name__); time.sleep(15)
    return None
BUDGET = float(os.environ.get("BUDGET_MIN", "320")) * 60; t_start = time.time(); MB = {}
for n, (s, t) in enumerate(need):
    if time.time() - t_start > BUDGET and not (MIN / f"{tick[s]}_{D[t]}.json").exists(): continue
    b = bars(s, t)
    if b: MB[(s, t)] = b
    if n % 50 == 0: print("minute", n, "/", len(need), round((time.time() - t_start) / 60), "min")
print("minute days ready", len(MB), "of", len(need))
def orh_entry(s, t, trig):
    """ORH entry from 5-minute bars: level = max(opening-range high, base high) + 1c; the first later bar over it fills
    at max(level, its open). Stop = the low of the day up to the entry, no wider than the ADR. The rest of the day is
    then checked bar by bar: a low at or under the stop closes the trade the same day."""
    b = MB.get((s, t))
    if not b: return None
    ses = [x for x in b if dt.time(9, 30) <= dt.datetime.fromtimestamp(x[0] / 1000, NY).time() < dt.time(16, 0)]
    if len(ses) < 3: return None
    k = max(x[2] for x in ses); f = H[s, t] / k if k else 1.0     # bars on the daily scale (splits since)
    if abs(f - 1) < 0.02: f = 1.0
    ses = [[x[0], x[1] * f, x[2] * f, x[3] * f, x[4] * f] for x in ses]
    no = max(1, P["orm"] // 5); orh = max(x[2] for x in ses[:no]); lvl = max(orh, trig) + 0.01
    lod = min(x[3] for x in ses[:no])
    for i in range(no, len(ses)):
        x = ses[i]
        if x[2] > lvl:
            e = max(lvl, x[1]); return dict(e=e, lod=lod if x[1] >= lvl else min(lod, x[3]), rest=ses[i + 1:])
        lod = min(lod, x[3])
    return None

# ---- simulation ----
def run(trail, pday, breadth):
    TR = MA10 if trail == 10 else MA20
    eq = 1.0; cash = 1.0; pos = {}; trades = []; curve = []; expo = 0
    for t in range(S0, T):
        # manage open positions
        for s in list(pos):
            q = pos[s]; o, h, l, c = O[s, t], H[s, t], L[s, t], C[s, t]
            if np.isnan(c): continue
            q["k"] += 1
            if l <= q["stop"]:
                px = min(o, q["stop"]) if not np.isnan(o) else q["stop"]
                cash += q["sh"] * px * (1 - P["cost"]); q["fills"].append((q["sh"], px)); q["why"] = "סטופ" if q["stop"] < q["e"] else "סטופ בנקודת הכניסה"
                q["x"] = t; trades.append(q); del pos[s]; continue
            if q["k"] == pday and not q["half"]:
                n = q["sh"] / 2; cash += n * c * (1 - P["cost"]); q["fills"].append((n, c)); q["sh"] -= n; q["half"] = True; q["stop"] = max(q["stop"], q["e"])
            elif q["half"] and c < TR[s, t]:
                cash += q["sh"] * c * (1 - P["cost"]); q["fills"].append((q["sh"], c)); q["why"] = f"סגירה מתחת לממוצע {trail}"
                q["x"] = t; trades.append(q); del pos[s]; continue
        # new entries (breakout today)
        if not breadth or BREADTH[t - 1] > 50:
            cand = [s for s in np.where(~np.isnan(TRIG[:, t]) & (H[:, t] > TRIG[:, t]))[0] if s not in pos]
            cand.sort(key=lambda s: -np.nan_to_num(R3[s, t - 1]))
            val = cash + sum(q["sh"] * C[s, t - 1] for s, q in pos.items())
            for s in cand:
                if len(pos) >= P["maxpos"]: break
                if np.isnan(O[s, t]): continue
                en = orh_entry(s, t, TRIG[s, t])
                if en is None: continue
                e = en["e"]; adr = ADR[s, t - 1]
                stop = max(en["lod"], e * (1 - adr)) if not np.isnan(adr) else en["lod"]
                if e - stop <= 0.0001 * e: stop = e * (1 - (adr if adr == adr else 0.05))
                sh = min(val * P["risk"] / (e - stop), val * P["cap"] / e)
                cost = sh * e * (1 + P["cost"])
                if cost > cash: sh = cash / (e * (1 + P["cost"])); cost = cash
                if sh <= 0: continue
                cash -= cost
                q = dict(s=s, i=t, e=e, stop=stop, st0=stop, sh=sh, sh0=sh, k=0, half=False, fills=[], mv=MOVE[s, t], bl=int(BLEN[s, t]))
                hit = next((x for x in en["rest"] if x[3] <= stop), None)
                if hit:                          # stopped out later the same day (from the 5-minute bars)
                    px = min(hit[1], stop); cash += sh * px * (1 - P["cost"]); q["fills"].append((sh, px)); q["why"] = "סטופ ביום הכניסה"; q["x"] = t; trades.append(q)
                else: pos[s] = q
        val = cash + sum(q["sh"] * np.nan_to_num(C[s, t], nan=q["e"]) for s, q in pos.items())
        expo += 1 if pos else 0; curve.append(val)
    for s, q in pos.items(): q["x"] = None; q["why"] = "פתוחה"; trades.append(q)
    return np.array(curve), trades, expo

def summ(curve, trades, expo):
    yrs = len(curve) / 252; cagr = curve[-1] ** (1 / yrs) - 1
    peak = np.maximum.accumulate(curve); dd = (curve / peak - 1).min()
    rs = []
    for q in trades:
        if q["x"] is None: continue
        got = sum(n * px for n, px in q["fills"]) * (1 - P["cost"]); paid = q["sh0"] * q["e"] * (1 + P["cost"])
        rs.append(got / paid - 1)
    rs = np.array(rs); w, lo = rs[rs > 0], rs[rs <= 0]
    return dict(cagr=round(cagr * 100, 1), dd=round(dd * 100, 1), n=len(rs), win=round(len(w) / max(1, len(rs)) * 100, 1),
                aw=round(w.mean() * 100, 1) if len(w) else 0, al=round(lo.mean() * 100, 1) if len(lo) else 0,
                pf=round(w.sum() / -lo.sum(), 2) if len(lo) and lo.sum() < 0 else None,
                expo=round(expo / len(curve) * 100), tot=round((curve[-1] - 1) * 100, 1))

def tlist(trades):
    out = []
    for q in sorted(trades, key=lambda q: q["i"], reverse=True):
        s = q["s"]
        if q["x"] is None:
            r = None
        else:
            got = sum(n * px for n, px in q["fills"]) * (1 - P["cost"]); r = round((got / (q["sh0"] * q["e"] * (1 + P["cost"])) - 1) * 100, 1)
        out.append([tick[s], D[q["i"]], round(q["e"], 2), round(q["st0"], 2), D[q["x"]] if q["x"] is not None else None,
                    (q["x"] - q["i"]) if q["x"] is not None else None, r, q["why"], round(q["mv"] * 100), q["bl"]])
    return out

spyc = np.array(spy["c"][S0:], dtype=float); spyc = spyc / spyc[0]
sp_dd = (spyc / np.maximum.accumulate(spyc) - 1).min()
res = {"asOf": D[-1], "from": D[S0], "params": P, "stocks": N,
       "spy": {"cagr": round((spyc[-1] ** (252 / len(spyc)) - 1) * 100, 1), "dd": round(sp_dd * 100, 1), "tot": round((spyc[-1] - 1) * 100, 1)},
       "dates": D[S0::5], "spyCurve": [round(float(x), 4) for x in spyc[::5]], "v": {}}
for trail in (10, 20):
    for pday in (3, 5):
        for br in (False, True):
            curve, trades, expo = run(trail, pday, br)
            k = f"t{trail}p{pday}{'b' if br else ''}"
            res["v"][k] = {"s": summ(curve, trades, expo), "curve": [round(float(x), 4) for x in curve[::5]], "trades": tlist(trades)}
            print(k, "done")   # results stay encrypted: nothing about them in the public log
# encrypt for the public site: AES-256-GCM, key from LAB_PASS by PBKDF2-SHA256 (310,000 rounds); lab.html decrypts in the browser
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
import base64
pw = os.environ.get("LAB_PASS", "")
if len(pw) < 10: sys.exit("LAB_PASS secret missing or shorter than 10 characters: nothing written")
salt, iv = os.urandom(16), os.urandom(12)
key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=310000).derive(pw.encode())
ct = AESGCM(key).encrypt(iv, json.dumps(res, ensure_ascii=False, separators=(",", ":")).encode(), None)
b64 = lambda x: base64.b64encode(x).decode()
OUT.write_text(json.dumps({"v": 1, "it": 310000, "salt": b64(salt), "iv": b64(iv), "ct": b64(ct)}))
print("wrote", OUT, round(OUT.stat().st_size / 1e3), "KB (encrypted)")
