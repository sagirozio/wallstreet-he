"""Builds the site from template.html + data.json (+ facts.json).

data.json stays the single source of truth (scripts and the scheduled content runs edit it).
This script derives everything the browser loads:
  index.html   – the app, with the light "core" data inlined (no profiles / per-stock lists)
  core.json    – the same core data, polled by the page every 5 minutes
  stocks.json  – the full stock universe (industry lists, exchanges, Hebrew names), loaded once in the background
  s/T.json     – per-stock details (profile, facts, next earnings date), loaded when a stock page opens
  stock/T.html – a static, indexable page per stock (for Google), linking into the app
  sitemap.xml
Files are only rewritten when their content changes, to keep git history small.
"""
import json, pathlib, re, html

root = pathlib.Path(__file__).resolve().parent.parent
SITE = "https://sagirozio.github.io/wallstreet-he/"

def load(p, default=None):
    p = root / p
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default

def write(rel, text):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists() and p.read_text(encoding="utf-8") == text:
        return False
    p.write_text(text, encoding="utf-8")
    return True

def js(o):
    return json.dumps(o, ensure_ascii=False, separators=(",", ":"))

data = load("data.json")
facts = load("facts.json", {}) or {}
he_names = load("scripts/he_names.json", {}) or {}
themes = data.get("themes") or {}
stocks = themes.get("stocks") or {}
exch = themes.get("ex") or {}
profiles = data.get("profiles") or {}
earn = data.get("earnDates") or {}
reports = data.get("reports") or []
news = data.get("news") or []

universe = {}                       # T -> (co, cap, industry)
for ind, lst in stocks.items():
    for s in lst:
        universe[s[0]] = (s[1], s[2], ind)

# ---------- core (inlined + polled) ----------
core = {k: v for k, v in data.items() if k not in ("profiles", "earnDates", "hl52")}
# reports: the page carries only the last 3 weeks; the full archive is reports.json (loaded on demand)
import datetime as _dt
_cut = (_dt.date.today() - _dt.timedelta(days=4)).isoformat()
core["reports"] = [r for r in reports if str(r.get("date", "")) >= _cut]
core["reportsN"] = len(reports)
write("reports.json", js(reports))
core["themes"] = {k: v for k, v in themes.items() if k not in ("stocks", "ex")}
core["themes"]["n"] = len(universe)
# breadth: the per-day stock lists go to breadth.json (loaded when the breadth section opens)
_b = core.get("breadth") or {}
write("breadth.json", js({"rows": [{"d": r.get("d"), "L": r.get("L")} for r in _b.get("rows", []) if r.get("L")]}))
core["breadth"] = {**_b, "rows": [{k: v for k, v in r.items() if k != "L"} for r in _b.get("rows", [])]}
core_txt = js(core)
write("core.json", core_txt)

# ---------- stock universe ----------
write("stocks.json", js({"asOf": themes.get("asOf"), "stocks": stocks, "ex": exch,
                         "he": {t: n for t, n in he_names.items() if t in universe}}))

# ---------- per-stock details ----------
n_s = 0
for t in sorted(set(universe) | set(profiles) | set(facts) | set(earn)):
    if not re.fullmatch(r"[A-Z0-9.\-]{1,10}", t):
        continue
    rec = {"p": profiles.get(t) or {}, "f": facts.get(t) or {}, "e": earn.get(t)}
    if rec["p"] or rec["f"] or rec["e"]:
        n_s += write(f"s/{t}.json", js(rec))

# ---------- index.html ----------
t = (root / "template.html").read_text(encoding="utf-8")
old = '  try { db = window.claude && await window.claude.use("db"); } catch(e) {}\n'
new = '''  try {
    for (let i=0; i<40 && !(window.claude && window.claude.use); i++) await new Promise(r=>setTimeout(r,250));
    if (window.claude && window.claude.use) db = await window.claude.use("db");
  } catch(e) {}
'''
page = t.replace(old, new).replace("__DATA__", core_txt.replace("</", "<\\/"))
write("index.html", page)

# ---------- static stock pages (SEO) ----------
SEC_HE = {"Technology": "טכנולוגיה", "Healthcare": "בריאות", "Financial Services": "פיננסים", "Consumer Cyclical": "צריכה מחזורית",
          "Consumer Defensive": "צריכה בסיסית", "Industrials": "תעשייה", "Energy": "אנרגיה", "Basic Materials": "חומרי גלם",
          "Real Estate": "נדל״ן", "Utilities": "תשתיות", "Communication Services": "תקשורת"}
ind_he = {r.get("en"): r.get("n") for r in themes.get("rows") or []}
ind_sec = themes.get("indSector") or {}
E = lambda s: html.escape(str(s if s is not None else ""), quote=True)

def dmy(d):
    m = re.fullmatch(r"(\d{4})-(\d\d)-(\d\d)", str(d or ""))
    return f"{m[3]}.{m[2]}.{m[1]}" if m else str(d or "")

def money(x):
    if not isinstance(x, (int, float)): return "—"
    a = abs(x); s = "-" if x < 0 else ""
    return f"{s}${a:.2f}B" if a >= 1 else f"{s}${a*1000:.1f}M"

def eps(x):
    return "—" if not isinstance(x, (int, float)) else ("-$" if x < 0 else "$") + f"{abs(x):.2f}"

last_rep = {}
for r in sorted(reports, key=lambda r: str(r.get("date", ""))):
    last_rep[r.get("t")] = r

def stock_news(tk, co):
    first = re.sub(r",? (Inc|Corp|Corporation|Ltd|plc|Holdings?|Group|Company|Co)\.?$", "", co or "", flags=re.I).split(" ")[0].lower()
    out = []
    for n in news:
        tt = n.get("t") or []
        hay = ((n.get("tag") or "") + " " + (n.get("title") or "")).lower()
        if (isinstance(tt, list) and tk in tt) or (len(first) > 2 and first in hay) or re.search(r"\b" + re.escape(tk) + r"\b", n.get("title") or ""):
            out.append(n)
        if len(out) >= 5: break
    return out

CSS = """body{margin:0;background:#0b0f17;color:#e8edf6;font-family:Heebo,system-ui,sans-serif;line-height:1.65;font-size:16px}
a{color:#5b8cff}.w{max-width:820px;margin:0 auto;padding:0 16px}header{border-bottom:1px solid #243049;padding:14px 0}
header a{color:#e8edf6;text-decoration:none;font-weight:800;font-size:20px;display:inline-flex;gap:8px;align-items:center}
header img{width:30px;height:30px}h1{font-size:26px;margin:22px 0 4px;line-height:1.3}h1 .tk{color:#8a97ae;font-size:17px;font-weight:600;direction:ltr;unicode-bidi:isolate}
h2{font-size:19px;margin:26px 0 8px}.meta{color:#8a97ae;font-size:14px}.cta{display:inline-block;margin:16px 0 4px;background:#5b8cff;color:#fff;
padding:12px 18px;border-radius:12px;text-decoration:none;font-weight:700}.card{background:#121826;border:1px solid #243049;border-radius:14px;padding:14px;margin:8px 0}
.facts{display:flex;gap:6px 18px;flex-wrap:wrap;color:#8a97ae;font-size:14px}.facts span{white-space:nowrap}.nw b{display:block}.nw small{color:#8a97ae}
.peers{display:flex;gap:8px;flex-wrap:wrap}.peers a{background:#182033;border:1px solid #243049;border-radius:9px;padding:6px 10px;text-decoration:none;color:#e8edf6;font-size:14px}
footer{color:#8a97ae;font-size:13px;border-top:1px solid #243049;margin-top:34px;padding:16px 0 40px}.num{direction:ltr;unicode-bidi:isolate}"""

def stock_page(tk):
    co, cap, ind = universe.get(tk, (None, None, None))
    r = last_rep.get(tk)
    if not co and r: co = r.get("co")
    co = co or tk
    heN = (he_names.get(tk) or "").split(" ")[0]
    prof = profiles.get(tk) or {}
    F = facts.get(tk) or {}
    sec = ind_sec.get(ind, "")
    secHe, indHe = SEC_HE.get(sec, (r or {}).get("sector", "")), ind_he.get(ind, "")
    title = f"מניית {heN + ' ' if heN else ''}{co} ({tk}) – תעודת זהות, דוחות וחדשות | וולסטריטר"
    desc = prof.get("desc") or f"{co} ({tk}) בעברית: על החברה, הדוח האחרון, תאריך הדוח הבא, חדשות וגרף מניה."
    desc = re.sub(r"\s+", " ", desc)
    if len(desc) > 158: desc = desc[:155].rsplit(" ", 1)[0] + "…"
    url = f"{SITE}stock/{tk}.html"
    app = f"../#stock/{tk}"
    parts = [f"<h1>{E(heN) + ' – ' if heN else ''}<bdi>{E(co)}</bdi> <small class=tk>{E(tk)}</small></h1>",
             f'<div class="meta">{" · ".join(E(x) for x in [secHe and "סקטור: " + secHe, indHe and "תעשייה: " + indHe, exch.get(tk)] if x)}</div>',
             f'<a class="cta" href="{E(app)}">לגרף, לנתונים ולעמוד המלא באתר ←</a>']
    about = prof.get("about") or prof.get("desc")
    fx = []
    if F.get("hq"): fx.append(f"<span>מטה: <bdi>{E(F['hq'])}</bdi></span>")
    if F.get("emp"): fx.append(f"<span>עובדים: <span class=num>{int(F['emp']):,}</span></span>")
    if F.get("web"):
        host = re.sub(r"^https?://(www\.)?", "", F["web"]).rstrip("/")
        fx.append(f'<a href="{E(F["web"])}" rel="nofollow noopener">{E(host)}</a>')
    if about or fx:
        parts.append("<h2>על החברה</h2>" + "".join(f"<p>{E(p)}</p>" for p in re.split(r"\n+", about or "") if p.strip())
                     + (f'<div class="facts">{"".join(fx)}</div>' if fx else ""))
    e = earn.get(tk)
    if e and e.get("d"):
        parts.append(f"<h2>הדוח הבא</h2><p>{dmy(e['d'])}{' (הערכה)' if e.get('est') else ''}</p>")
    if r:
        rows = [f"<b>{E(r.get('q'))} · פורסם ב-{dmy(r.get('date'))}</b>",
                f"רווח למניה: <span class=num>{eps(r.get('epsAct'))}</span> (צפי <span class=num>{eps(r.get('epsEst'))}</span>)"]
        if isinstance(r.get("revAct"), (int, float)):
            rows.append(f"מכירות: <span class=num>{money(r.get('revAct'))}</span> (צפי <span class=num>{money(r.get('revEst'))}</span>)")
        if r.get("guideText"): rows.append("תחזית: " + E(r["guideText"]))
        if r.get("note"): rows.append(E(r["note"]))
        parts.append('<h2>הדוח האחרון</h2><div class="card">' + "<br>".join(rows) + "</div>")
    nn = stock_news(tk, co)
    if nn:
        parts.append("<h2>חדשות אחרונות</h2>" + "".join(
            f'<div class="card nw"><small>{dmy(n.get("date"))}</small><b>{E(n.get("title"))}</b>{E(n.get("body"))}</div>' for n in nn))
    peers = [s for s in stocks.get(ind, []) if s[0] != tk][:10]
    if peers:
        parts.append(f"<h2>חברות נוספות בתעשייה{(': ' + E(indHe)) if indHe else ''}</h2><div class=\"peers\">" +
                     "".join(f'<a href="{E(p[0])}.html">{E(p[0])} · {E(p[1])}</a>' for p in peers) + "</div>")
    ld = {"@context": "https://schema.org", "@type": "Corporation", "name": co, "tickerSymbol": tk}
    if F.get("web"): ld["url"] = F["web"]
    return f"""<!DOCTYPE html>
<html lang="he" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{E(title)}</title><meta name="description" content="{E(desc)}"><link rel="canonical" href="{url}">
<meta property="og:title" content="{E(title)}"><meta property="og:description" content="{E(desc)}"><meta property="og:url" content="{url}">
<meta property="og:site_name" content="וולסטריטר"><meta property="og:locale" content="he_IL"><meta name="theme-color" content="#0b0f17">
<link rel="icon" type="image/svg+xml" href="../logo.svg"><link rel="manifest" href="../manifest.webmanifest">
<script type="application/ld+json">{js(ld).replace("</", "<\\/")}</script><link rel="stylesheet" href="../stock.css"></head>
<body><header><div class="w"><a href="../"><img src="../logo.svg" alt="">וולסטריטר</a></div></header>
<main class="w">{"".join(parts)}</main>
<footer class="w">וולסטריטר – השוק האמריקאי, בגובה העיניים. המידע באתר הוא מידע כללי בלבד ואינו ייעוץ השקעות או המלצה לקנות או למכור ניירות ערך.
<a href="../#terms">תנאי שימוש</a> · <a href="../">לעמוד הראשי</a></footer></body></html>
"""

write("stock.css", CSS + "\n")
pages = sorted(t for t in set(universe) | {r.get("t") for r in reports if r.get("t")} if re.fullmatch(r"[A-Z0-9.\-]{1,10}", t or ""))
n_p = sum(write(f"stock/{tk}.html", stock_page(tk)) for tk in pages)

sm = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">', f"<url><loc>{SITE}</loc></url>"]
sm += [f"<url><loc>{SITE}stock/{tk}.html</loc></url>" for tk in pages]
write("sitemap.xml", "\n".join(sm + ["</urlset>", ""]))

print(f"built: index.html {len(page)//1024}KB, core.json {len(core_txt)//1024}KB, {len(pages)} stock pages ({n_p} changed), {n_s} stock files changed")
