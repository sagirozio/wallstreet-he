"""Publish the intraday tables (sectors, breadth + today's stock lists, movers, pre-market) to the `intra` branch
as intra.json (orphan, force-pushed: no history, no commits on main every 10 minutes). The site reads it from
raw.githubusercontent.com and uses it while its `ts` is newer than core.json's (the nightly update)."""
import json, os, time, pathlib, tempfile, subprocess
root = pathlib.Path(__file__).resolve().parent.parent
d = json.loads((root / "data.json").read_text(encoding="utf-8"))
REPO = os.environ.get("GITHUB_REPOSITORY", "sagirozio/wallstreet-he"); TOKEN = os.environ["GH_TOKEN"]
b = d.get("breadth") or {}; rows = b.get("rows") or []
out = {"ts": int(time.time()),
       "sectors": d.get("sectors"), "movers": d.get("movers"), "premarket": d.get("premarket"), "crypto": d.get("crypto"),
       "breadth": {**b, "rows": [{k: v for k, v in r.items() if k != "L"} for r in rows]},
       "brL": {rows[0]["d"]: rows[0]["L"]} if rows and rows[0].get("L") else {}}
with tempfile.TemporaryDirectory() as t:
    (pathlib.Path(t) / "intra.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    g = lambda *a: subprocess.run(["git", "-c", "user.name=wallstreet-bot", "-c", "user.email=bot@users.noreply.github.com", *a], cwd=t, check=True, capture_output=True)
    g("init", "-q"); g("checkout", "-q", "--orphan", "intra"); g("add", "intra.json"); g("commit", "-qm", "intraday tables")
    g("push", "-fq", f"https://x-access-token:{TOKEN}@github.com/{REPO}.git", "intra")
print("intra.json published", len(json.dumps(out)) // 1024, "KB")
