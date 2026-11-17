"""Morning health check: is every table fresh and plausible, did the jobs run? Problems -> one GitHub issue
("בדיקת בריאות") that is opened / updated / closed automatically, so the owner gets a GitHub notification."""
import json, os, re, pathlib, urllib.request, datetime as dt
from zoneinfo import ZoneInfo
root = pathlib.Path(__file__).resolve().parent.parent
d = json.loads((root / "data.json").read_text(encoding="utf-8"))
REPO = os.environ.get("GITHUB_REPOSITORY", "sagirozio/wallstreet-he"); TOK = os.environ.get("GH_TOKEN", "")
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
