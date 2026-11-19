"""Daily watchlist alert mails for signed-in users.

Reads the users from Clerk's server API (CLERK_SECRET_KEY): each user's watchlist and alert settings live in
unsafe_metadata ({"watch": [...], "alerts": {"on":1, "mv":5, "er":1, "vb":1, "hi":1}}). For every user with alerts on,
it collects today's facts about the stocks on the list and sends one summary mail through Resend (RESEND_KEY).
Nothing is sent on a day with nothing to report. One mail per user per session date: the dates already sent are kept
on the orphan branch "alerts" (sent.json), so a second run the same night does not send again.

Facts only, no recommendations. Run after the close (alerts.yml).
Usage: python scripts/alerts.py [--dry]   (--dry prints the mails instead of sending)
"""
import json, os, sys, pathlib, subprocess, tempfile, urllib.request, datetime as dt, html
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parent.parent
REPO = os.environ.get("GITHUB_REPOSITORY", "sagirozio/wallstreet-he")
CLERK = os.environ.get("CLERK_SECRET_KEY", "")
RESEND = os.environ.get("RESEND_KEY", "")
FROM = os.environ.get("ALERTS_FROM", "וולסטריטר <alerts@wallstreeter.co.il>")
SITE = "https://wallstreeter.co.il"
DRY = "--dry" in sys.argv


def get(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    return json.loads(urllib.request.urlopen(req, timeout=40).read().decode())


def git_show(branch, path):
    r = subprocess.run(["git", "show", f"origin/{branch}:{path}"], cwd=ROOT, capture_output=True)
    return json.loads(r.stdout.decode()) if r.returncode == 0 and r.stdout else None


def clerk_users():
    out, off = [], 0
    while True:
        page = get(f"https://api.clerk.com/v1/users?limit=100&offset={off}&order_by=-created_at",
                   {"Authorization": f"Bearer {CLERK}"})
        out += page
        if len(page) < 100:
            return out
        off += 100


def main():
    if not CLERK:
        print("no CLERK_SECRET_KEY: nothing to do"); return
    for b in ("live", "alerts"):                       # separately: the alerts branch does not exist before the first mail
        subprocess.run(["git", "fetch", "-q", "origin", f"+{b}:refs/remotes/origin/{b}"], cwd=ROOT, capture_output=True)
    live = git_show("live", "live.json") or {}
    day = live.get("date")                              # the session the live prices belong to (New York date)
    if not day:
        print("no live date"); return
    ny_now = dt.datetime.now(ZoneInfo("America/New_York"))
    if live.get("state") not in ("POST", "POSTPOST", "CLOSED") and ny_now.hour < 16:
        print("market not closed yet"); return
    q = live.get("q") or {}
    vb = live.get("vb") or {}
    stocks = json.loads((ROOT / "stocks.json").read_text(encoding="utf-8"))
    ix = {r[0]: r for rows in stocks["stocks"].values() for r in rows}          # [t, co, cap, {d,w,...,hi,rs}]
    reports = json.loads((ROOT / "reports.json").read_text(encoding="utf-8"))
    rep_today = {}
    for r in reports:
        if r.get("date") in (day,):
            rep_today[r["t"]] = r
    screen = json.loads((ROOT / "screen.json").read_text(encoding="utf-8")).get("x", {})
    nxt = dt.date.fromisoformat(day) + dt.timedelta(days=1)
    while nxt.weekday() >= 5:
        nxt += dt.timedelta(days=1)
    nxt = nxt.isoformat()
    sent = git_show("alerts", "sent.json") or {}

    def facts(t, A):
        F = []
        L = q.get(t)
        ch = L[1] if L else ((ix.get(t) or [None] * 4)[3] or {}).get("d")
        px = L[0] if L else None
        if A.get("mv") and ch is not None and abs(ch) >= float(A["mv"]):
            F.append(("move", f"{'עלתה' if ch > 0 else 'ירדה'} {abs(ch):.1f}% היום" + (f", לסגירה של ${px:,.2f}" if px else "")))
        if A.get("vb") and t in vb:
            c, r = vb[t]
            F.append(("vb", f"פריצה במחזור: {c:+.1f}% במחזור של פי {r} מהממוצע"))
        if A.get("hi"):
            r = (ix.get(t) or [None] * 4)[3] or {}
            if r.get("hi") is not None and r["hi"] >= -0.3 and (ch or 0) > 0:
                F.append(("hi", "סגרה בשיא של 52 שבועות"))
        if A.get("er"):
            rp = rep_today.get(t)
            if rp:
                s = f"פרסמה דוח ({rp.get('q', '')})"
                if rp.get("epsAct") is not None and rp.get("epsEst") is not None:
                    s += f": רווח למניה ${rp['epsAct']} מול צפי ${rp['epsEst']}"
                if rp.get("revAct") is not None and rp.get("revEst") is not None:
                    s += f", הכנסות ${rp['revAct']}B מול צפי ${rp['revEst']}B"
                F.append(("er", s))
            elif (screen.get(t) or {}).get("e") == nxt:
                F.append(("er", f"מפרסמת דוח ב-{int(nxt[8:])}.{int(nxt[5:7])}"))
        return F

    users = clerk_users()
    n_sent = 0
    for u in users:
        meta = u.get("unsafe_metadata") or {}
        A = meta.get("alerts") or {}
        watch = [t for t in (meta.get("watch") or []) if isinstance(t, str)][:60]
        if not A.get("on") or not watch or sent.get(u["id"]) == day:
            continue
        mail = next((e["email_address"] for e in u.get("email_addresses", []) if e["id"] == u.get("primary_email_address_id")), None)
        if not mail:
            continue
        rows = [(t, f) for t in watch for f in [facts(t, A)] if f]
        if not rows:
            continue
        d = f"{int(day[8:])}.{int(day[5:7])}"
        name = html.escape(u.get("first_name") or "")
        items = "".join(
            f'<tr><td style="padding:10px 0;border-bottom:1px solid #eee;vertical-align:top">'
            f'<a href="{SITE}/#stock/{t}" style="color:#0b57d0;font-weight:700;text-decoration:none">{t}</a>'
            f'<div style="color:#666;font-size:13px">{html.escape(((ix.get(t) or [t, ""])[1]) or "")}</div></td>'
            f'<td style="padding:10px 12px 10px 0;border-bottom:1px solid #eee;font-size:15px;line-height:1.6">'
            + "<br>".join(html.escape(s) for _, s in f) + "</td></tr>"
            for t, f in rows)
        body = (f'<div dir="rtl" style="font-family:Arial,sans-serif;max-width:560px;margin:auto;color:#111">'
                f'<h2 style="margin:0 0 4px">הרשימה שלך – סגירת {d}</h2>'
                f'<p style="color:#555;margin:0 0 12px">{"שלום " + name + ", " if name else ""}זה מה שקרה היום במניות שבמעקב שלך.</p>'
                f'<table style="width:100%;border-collapse:collapse">{items}</table>'
                f'<p style="margin:18px 0"><a href="{SITE}" style="background:#2f81f7;color:#fff;padding:10px 18px;border-radius:8px;text-decoration:none">לאתר</a></p>'
                f'<p style="color:#888;font-size:12px;line-height:1.6">מידע עובדתי בלבד, לא ייעוץ השקעות ולא המלצה. '
                f'קיבלת את המייל כי הפעלת התראות בחשבון שלך בוולסטריטר. לביטול: באתר, "הרשימה שלי" ← התראות במייל ← לכבות.</p></div>')
        subj = f"הרשימה שלך – סגירת {d}: " + ", ".join(t for t, _ in rows[:4]) + (" ועוד" if len(rows) > 4 else "")
        if DRY:
            print("TO", mail, "|", subj); print("\n".join(f"  {t}: {f}" for t, f in rows)); continue
        if not RESEND:
            print("no RESEND_KEY: not sending"); return
        req = urllib.request.Request("https://api.resend.com/emails", method="POST",
                                     data=json.dumps({"from": FROM, "to": [mail], "subject": subj, "html": body}).encode(),
                                     headers={"Authorization": f"Bearer {RESEND}", "Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req, timeout=30).read(); sent[u["id"]] = day; n_sent += 1
        except Exception as e:
            print("send failed", u["id"], str(e)[:200])
    print(f"users {len(users)}, mails sent {n_sent}, session {day}")
    if n_sent and not DRY:
        tok = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
        url = f"https://x-access-token:{tok}@github.com/{REPO}.git" if tok else "origin"
        with tempfile.TemporaryDirectory() as t:
            g = lambda *a: subprocess.run(["git", "-c", "user.name=wallstreet-bot", "-c", "user.email=bot@users.noreply.github.com", *a], cwd=t, check=True, capture_output=True)
            (pathlib.Path(t) / "sent.json").write_text(json.dumps(sent))
            g("init", "-q"); g("checkout", "-q", "--orphan", "alerts"); g("add", "-A"); g("commit", "-qm", f"alerts sent {day}"); g("push", "-fq", url, "alerts")


if __name__ == "__main__":
    main()
