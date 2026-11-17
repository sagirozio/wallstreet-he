"""Gate for the nightly update (it is started several times a night because GitHub drops scheduled starts):
run once after the US close, and once more after 05:00 UTC (Massive has the previous session by then). Exit 1 = skip."""
import json, pathlib, datetime as dt, sys
from zoneinfo import ZoneInfo
d = json.loads((pathlib.Path(__file__).resolve().parent.parent / "data.json").read_text(encoding="utf-8"))
ts = dt.datetime.fromtimestamp(d.get("ts", 0), dt.timezone.utc)
now = dt.datetime.now(dt.timezone.utc); ny = now.astimezone(ZoneInfo("America/New_York"))
day = ny.date() if ny.hour * 60 + ny.minute >= 16 * 60 + 10 else ny.date() - dt.timedelta(days=1)
while day.weekday() >= 5: day -= dt.timedelta(days=1)
close = dt.datetime.combine(day, dt.time(16, 10), ZoneInfo("America/New_York")).astimezone(dt.timezone.utc)
morning = now.replace(hour=5, minute=0, second=0, microsecond=0)
need = ts < close or (now >= morning and ts < morning and morning > close)
print("last update", ts.isoformat(), "| last close", close.isoformat(), "->", "run" if need else "skip")
sys.exit(0 if need else 1)
