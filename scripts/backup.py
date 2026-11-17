"""Nightly backup of data.json to the `backup` branch (orphan, force-pushed): keeps the last 14 copies.
Restore: git show origin/backup:data-YYYY-MM-DD.json > data.json"""
import os, pathlib, tempfile, subprocess, datetime as dt
root = pathlib.Path(__file__).resolve().parent.parent
REPO = os.environ.get("GITHUB_REPOSITORY", "sagirozio/wallstreet-he"); TOKEN = os.environ["GH_TOKEN"]
URL = f"https://x-access-token:{TOKEN}@github.com/{REPO}.git"
with tempfile.TemporaryDirectory() as t:
    g = lambda *a: subprocess.run(["git", "-c", "user.name=wallstreet-bot", "-c", "user.email=bot@users.noreply.github.com", *a], cwd=t, check=True, capture_output=True, text=True)
    g("init", "-q")
    if subprocess.run(["git", "fetch", "-q", "--depth=1", URL, "backup"], cwd=t).returncode == 0:
        g("checkout", "-q", "FETCH_HEAD", "--", ".")
    g("checkout", "-q", "--orphan", "backup")
    p = pathlib.Path(t); (p / f"data-{dt.date.today()}.json").write_bytes((root / "data.json").read_bytes())
    files = sorted(p.glob("data-*.json"))
    for f in files[:-14]: f.unlink()
    g("add", "-A"); g("commit", "-qm", f"backup {dt.date.today()}")
    g("push", "-fq", URL, "backup")
    print("backups:", [f.name for f in sorted(p.glob("data-*.json"))])
