"""Intraday data loop (replaces the every-15-min cron jobs, which GitHub often delays or drops).

One GitHub Actions job runs this for up to ~5h50m and repeats every 10 minutes:
  pre-market (04:00–09:30 New York): premarket.py (SPY/QQQ pre-market quotes)
  session    (09:30–16:15 New York): update.py (sectors, breadth, movers) + premarket.py (after-hours box)
Each round starts from the latest data.json on main and publishes the result to the `intra` branch (intra_publish.py):
no commits on main during the day (the nightly update commits the official tables). After each session round,
health.py live checks that live.json / intra.json are fresh and opens a GitHub issue if they get stuck.
loop.yml starts it three times a day; each new start cancels the previous run, so the day is covered even if one start is late.
"""
import subprocess, time, datetime as dt
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
START = time.time()
EVERY = 600

def sh(cmd):
    print("$", cmd, flush=True)
    return subprocess.run(cmd, shell=True).returncode

while True:
    ny = dt.datetime.now(NY)
    m = ny.hour * 60 + ny.minute
    if ny.weekday() >= 5 or m > 16 * 60 + 15 or time.time() - START > 350 * 60:
        print("loop done", ny.strftime("%H:%M ET"), flush=True)
        break
    if m < 4 * 60:
        time.sleep(60)
        continue
    t0 = time.time()
    sh("git fetch -q origin main && git checkout -q origin/main -- data.json")
    if m < 9 * 60 + 30:
        sh("timeout 300 python scripts/premarket.py")
        msg = "Pre-market update"
    else:
        sh("timeout 480 python scripts/update_live.py")
        sh("timeout 300 python scripts/premarket.py || true")
        msg = "Intraday update"
    print(msg, flush=True)
    sh("timeout 120 python scripts/intra_publish.py")
    if m >= 9 * 60 + 45: sh("timeout 120 python scripts/health.py live || true")
    time.sleep(max(30, EVERY - (time.time() - t0)))
