"""Merge hand-written Hebrew company texts (scripts/_ab/bNN.json: {T: [one-line desc, about]}) into data.json profiles."""
import json, pathlib, sys
root = pathlib.Path(__file__).resolve().parents[2]
p = root / "data.json"; d = json.loads(p.read_text(encoding="utf-8")); P = d.setdefault("profiles", {})
n = 0
for f in sys.argv[1:]:
    for t, (desc, about) in json.loads(pathlib.Path(f).read_text(encoding="utf-8")).items():
        pr = P.setdefault(t, {})
        pr["desc"] = desc
        if not pr.get("about"): pr["about"] = desc + " " + about if not about.startswith(desc[:20]) else about
        n += 1
p.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
print("merged", n)
