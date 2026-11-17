"""Builds index.html from template.html + data.json."""
import json, pathlib
root = pathlib.Path(__file__).resolve().parent.parent
t = (root / "template.html").read_text(encoding="utf-8")
data = json.loads((root / "data.json").read_text(encoding="utf-8"))
_facts = root / "facts.json"   # HQ / employees / website per ticker, written by scripts/about.py
if _facts.exists(): data["facts"] = json.loads(_facts.read_text(encoding="utf-8"))
old = '  try { db = window.claude && await window.claude.use("db"); } catch(e) {}\n'
new = '''  try {
    for (let i=0; i<40 && !(window.claude && window.claude.use); i++) await new Promise(r=>setTimeout(r,250));
    if (window.claude && window.claude.use) db = await window.claude.use("db");
  } catch(e) {}
'''
html = t.replace(old, new).replace("__DATA__", json.dumps(data, ensure_ascii=False))
(root / "index.html").write_text(html, encoding="utf-8")
print("index.html built", len(html))
