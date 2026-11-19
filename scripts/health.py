"""Morning health check: is every table fresh and plausible, did the jobs run? Problems -> one GitHub issue
("בדיקת בריאות") that is opened / updated / closed automatically, so the owner gets a GitHub notification."""
import json, os, re, pathlib, urllib.request, datetime as dt
from zoneinfo import ZoneInfo
root = pathlib.Path(__file__).resolve().parent.parent
import sys
REPO = os.environ.get("GITHUB_REPOSITORY", "sagirozio/wallstreet-he"); TOK = os.environ.get("GH_TOKEN", "")
def gh(method, path, body=None):
    req = urllib.request.Request(f"https://api.github.com/repos/{REPO}{path}", method=method, data=json.dumps(body).encode() if body else None,
                                 headers={"Authorization": f"Bearer {TOK}", "Accept": "application/vnd.github+json"})
    return json.loads(urllib.request.urlopen(req, timeout=30).read().decode() or "null")
if sys.argv[1:] == ["live"]:
    # ---- during the session (called by loop.py every 10 min): are the live files moving? ----
    RAW = f"https://raw.githubusercontent.com/{REPO}"
    def get(u):
        try: return json.loads(urllib.request.urlopen(f"{u}?x={int(dt.datetime.now().timestamp())}", timeout=30).read().decode())
        except Exception as e: return {"_err": str(e)}
    now = dt.datetime.now(dt.timezone.utc); P = []
    L = get(f"{RAW}/live/live.json")
    m = re.match(r"(\d{2})\.(\d{2})\.(\d{4}) · (\d{2}):(\d{2})", L.get("asOf", ""))
    lt = dt.datetime(int(m[3]), int(m[2]), int(m[1]), int(m[4]), int(m[5]), tzinfo=ZoneInfo("Asia/Jerusalem")) if m else None
    age = (now - lt).total_seconds() / 60 if lt else None
    if age is None or age > 20: P.append(f"המחירים החיים (live.json) לא התעדכנו {round(age) if age else '?'} דקות")
    elif L.get("state") == "REGULAR":
        q = L.get("q") or {}
        if len(q) < 1700: P.append(f"המחירים החיים: רק {len(q)} מניות")
        I = get(f"{RAW}/intra/intra.json")
        ia = (now.timestamp() - I.get("ts", 0)) / 60
        if ia > 25: P.append(f"טבלאות זמן המסחר (intra.json) לא התעדכנו {round(ia)} דקות")
        rows = (I.get("breadth") or {}).get("rows") or []; r0 = rows[0] if rows else {}; BL = (I.get("brL") or {}).get(r0.get("d"))
        if not BL: P.append("רוחב שוק: אין רשימות מניות להיום")
        elif [len(BL["hi"]), len(BL["lo"]), len(BL["u"]), len(BL["n"])] != [r0.get("hi"), r0.get("lo"), r0.get("up10"), r0.get("dn10")]:
            P.append("רוחב שוק: הרשימות לא תואמות לספירות")
        if r0.get("up", 0) + r0.get("dn", 0) < 400: P.append(f"רוחב שוק: רק {r0.get('up', 0) + r0.get('dn', 0)} מניות בספירת עלו/ירדו")
    # self-repair: live.json stuck during US hours -> make sure a live run is going (restart a stuck one)
    nyh = dt.datetime.now(ZoneInfo("America/New_York")); nym = nyh.hour * 60 + nyh.minute
    if TOK and age is not None and age > 15 and nyh.weekday() < 5 and 4 * 60 <= nym < 20 * 60:
        try:
            runs = (gh("GET", "/actions/workflows/live.yml/runs?per_page=10") or {}).get("workflow_runs", [])
            act = [r for r in runs if r.get("status") == "in_progress"]; que = [r for r in runs if r.get("status") in ("queued", "pending", "waiting")]
            if act and age > 30:
                gh("POST", f"/actions/runs/{act[0]['id']}/cancel"); P.append("הריצה של המחירים החיים נתקעה: בוטלה והופעלה מחדש")
                if not que: gh("POST", "/actions/workflows/live.yml/dispatches", {"ref": "main"})
            elif not act and not que:
                gh("POST", "/actions/workflows/live.yml/dispatches", {"ref": "main"}); P.append("המחירים החיים לא רצו: הופעלו מחדש אוטומטית")
        except Exception as e: print("self-repair failed", e)
    print("\n".join(P) or "live ok")
    # open an issue only after 2 failing checks in a row (one slow round is normal)
    cnt = pathlib.Path("/tmp/health_live_fails"); n = int(cnt.read_text()) + 1 if P and cnt.exists() else (1 if P else 0); cnt.write_text(str(n))
    if TOK:
        iss = gh("GET", "/issues?state=open&labels=health-live&per_page=5") or []
        stamp = dt.datetime.now(ZoneInfo("Asia/Jerusalem")).strftime("%d.%m %H:%M")
        if n == 2 or (n > 2 and n % 6 == 0):   # first alert, then once an hour
            body = f"בדיקה בזמן המסחר, {stamp} (שעון ישראל)\n\n" + "\n".join(f"- {x}" for x in P)
            if iss: gh("POST", f"/issues/{iss[0]['number']}/comments", {"body": body})
            else: gh("POST", "/issues", {"title": "בזמן המסחר: נתונים לא מתעדכנים", "body": body, "labels": ["health-live"]})
        elif not P and iss and "בזמן המסחר" in iss[0].get("title", ""):
            gh("POST", f"/issues/{iss[0]['number']}/comments", {"body": f"חזר לעבוד ✓ ({stamp})"}); gh("PATCH", f"/issues/{iss[0]['number']}", {"state": "closed"})
    raise SystemExit(0)
d = json.loads((root / "data.json").read_text(encoding="utf-8"))
ny = dt.datetime.now(ZoneInfo("America/New_York")).date()
exp = ny - dt.timedelta(days=1)                      # last completed session (holidays not modelled)
while exp.weekday() >= 5: exp -= dt.timedelta(days=1)
def date_of(s):
    m = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", s or ""); return dt.date(int(m[3]), int(m[2]), int(m[1])) if m else None
P = []
for name, s in [("טבלת התעשיות", d.get("themes", {}).get("asOf")), ("סקטורים", d.get("sectors", {}).get("asOf")),
                ("רוחב שוק", d.get("breadth", {}).get("asOf")), ("הכפילו ב-2026", d.get("ytd", {}).get("asOf")),
                ("זינקו בחודש", d.get("gainers", {}).get("asOf"))]:
    x = date_of(s)
    if not x or x < exp: P.append(f"{name}: הנתונים מ-{x or 'לא ידוע'}, מצופה {exp:%d.%m}")
T = d.get("themes", {}); st = T.get("stocks", {})
for r in T.get("rows", []):
    n = len(st.get(r["en"], []))
    if n >= 3 and abs(r.get("d") or 0) > 15: P.append(f"תעשייה {r['en']}: שינוי יומי חשוד {r['d']}% ({n} מניות)")
    if n >= 3 and abs(r.get("m") or 0) > 120: P.append(f"תעשייה {r['en']}: שינוי חודשי חשוד {r['m']}% ({n} מניות)")
if len(T.get("rows", [])) < 120: P.append(f"טבלת התעשיות: רק {len(T.get('rows', []))} תעשיות")
nst = sum(len(v) for v in st.values())
if nst < 1700: P.append(f"רק {nst} מניות ביקום (בדרך כלל ~1,950)")
chk = T.get("check") or {}
if chk.get("histTo") and (exp - dt.date.fromisoformat(chk["histTo"])).days > 4: P.append(f"מאגר המחירים של Massive עומד על {chk['histTo']}")
# failed workflow runs in the last 24h
if TOK:
    try:
        req = urllib.request.Request(f"https://api.github.com/repos/{REPO}/actions/runs?per_page=60", headers={"Authorization": f"Bearer {TOK}"})
        runs = json.loads(urllib.request.urlopen(req, timeout=30).read().decode())["workflow_runs"]
        since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=24)
        bad = sorted({r["name"] for r in runs if r.get("conclusion") == "failure" and dt.datetime.fromisoformat(r["created_at"].replace("Z", "+00:00")) > since})
        for b in bad: P.append(f"ריצה נכשלה ב-24 השעות האחרונות: {b}")
    except Exception as e: print("runs check failed", e)
print("\n".join(P) or "הכל תקין")
# one issue, reused
if TOK:
    H = {"Authorization": f"Bearer {TOK}", "Accept": "application/vnd.github+json"}
    def call(method, path, body=None):
        req = urllib.request.Request(f"https://api.github.com/repos/{REPO}{path}", method=method, headers=H, data=json.dumps(body).encode() if body else None)
        return json.loads(urllib.request.urlopen(req, timeout=30).read().decode() or "null")
    issues = [i for i in call("GET", "/issues?state=open&labels=health&per_page=5") or []]
    body = f"בדיקה של {dt.datetime.now(ZoneInfo('Asia/Jerusalem')):%d.%m.%Y %H:%M} (שעון ישראל), יום מסחר מצופה: {exp:%d.%m}\n\n" + "\n".join(f"- {p}" for p in P)
    if P:
        if issues: call("POST", f"/issues/{issues[0]['number']}/comments", {"body": body})
        else: call("POST", "/issues", {"title": "בדיקת בריאות: יש בעיה בנתונים", "body": body, "labels": ["health"]})
    elif issues:
        call("POST", f"/issues/{issues[0]['number']}/comments", {"body": "הכל תקין שוב ✓"}); call("PATCH", f"/issues/{issues[0]['number']}", {"state": "closed"})
