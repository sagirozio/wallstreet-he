"""Intraday data loop (replaces the every-15-min cron jobs, which GitHub often delays or drops).

One GitHub Actions job runs this for up to ~5h50m and repeats every 3 minutes:
  pre-market (04:00–09:30 New York): premarket.py (SPY/QQQ pre-market quotes)
  session    (09:30–16:15 New York): update.py (sectors, breadth, movers) + premarket.py (after-hours box)
Each round starts from the latest data.json on main and publishes the result to the `intra` branch (intra_publish.py):
no commits on main during the day (the nightly update commits the official tables). After each session round,
health.py live checks that live.json / intra.json are fresh and opens a GitHub issue if they get stuck.
loop.yml tries to start it every hour; a start while one is running waits in the queue (no cancel), so the day stays covered even
when GitHub delays or drops scheduled starts. Hourly in the background: news_hourly.sh (Finnhub headlines + same-day cards).
"""
import os, subprocess, time, datetime as dt
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
START = time.time()
EVERY = 180
NEWS, NEWS_AT = None, 0.0
KICKED = set()
def kick(wf, extra=""):   # start another workflow (GitHub's own schedule drops runs)
    if wf in KICKED: return
    KICKED.add(wf); sh(f'gh api -X POST repos/{os.environ.get("GITHUB_REPOSITORY", "sagirozio/wallstreet-he")}/actions/workflows/{wf}/dispatches -f ref=main {extra} || true')   # background hourly headlines job (news_hourly.sh)

def sh(cmd):
    print("$", cmd, flush=True)
    return subprocess.run(cmd, shell=True).returncode

while True:
    ny = dt.datetime.now(NY)
    m = ny.hour * 60 + ny.minute
    if ny.weekday() >= 5 or m > 16 * 60 + 15 or time.time() - START > 350 * 60:
        print("loop done", ny.strftime("%H:%M ET"), flush=True)
        if ny.weekday() < 5 and m <= 16 * 60 + 15: kick("loop.yml")   # hit the 6-hour job limit mid-session: continue in a new run
        else:
            if ny.weekday() == 4: kick("analysts.yml")   # weekly analyst data, Friday after the close
            kick("update.yml"); kick("backup.yml")    # the nightly update right after the close + nightly data backup
        if NEWS is not None and NEWS.poll() is None: NEWS.wait(timeout=1800)
        break
    if m < 4 * 60:
        time.sleep(60)
        continue
    t0 = time.time()
    if m >= 9 * 60 + 15: kick("live.yml")          # live quotes for the session
    if m < 9 * 60:                                 # morning jobs GitHub's schedule tends to drop
        kick("insiders.yml"); kick("health.yml"); kick("fundamentals.yml", "-f 'inputs[tickers]=--recent 3'")
    # hourly from 07:30 New York (14:30 Israel): headlines + same-day earnings cards, in the background
    if m >= 7 * 60 + 30 and (NEWS is None or NEWS.poll() is not None) and time.time() - NEWS_AT >= 55 * 60:
        print("$ news_hourly.sh (background)", flush=True)
        NEWS = subprocess.Popen(["bash", "scripts/news_hourly.sh"]); NEWS_AT = time.time()
    sh("git fetch -q origin main && git checkout -q origin/main -- data.json scripts")
    if m < 9 * 60 + 30:
        sh("timeout 300 python scripts/premarket.py")
        if m >= 7 * 60: sh("timeout 240 python scripts/premovers.py || true")   # pre-market 10%+ movers (from 14:00 Israel)
        msg = "Pre-market update"
    else:
        sh("timeout 480 python scripts/update_live.py")
        sh("timeout 300 python scripts/premarket.py || true")
        msg = "Intraday update"
    print(msg, flush=True)
    sh("timeout 120 python scripts/intra_publish.py")
    if m >= 9 * 60 + 45: sh("timeout 120 python scripts/health.py live || true")
    time.sleep(max(30, EVERY - (time.time() - t0)))
