"""Check that the custom domain points to GitHub Pages (used once when connecting the domain)."""
import socket, sys
for h in ["wallstreeter.co.il", "www.wallstreeter.co.il"]:
    try: print(h, sorted({a[4][0] for a in socket.getaddrinfo(h, 80, socket.AF_INET)}))
    except Exception as e: print(h, "ERR", e)
try: print("www cname ->", socket.gethostbyname_ex("www.wallstreeter.co.il")[0:2])
except Exception as e: print("cname ERR", e)
import urllib.request, ssl
for u in ["http://wallstreeter.co.il/", "https://wallstreeter.co.il/", "https://sagirozio.github.io/wallstreet-he/"]:
    try:
        r = urllib.request.urlopen(u, timeout=20); b = r.read(3000).decode("utf-8", "replace")
        print("fetch", u, "->", r.status, r.geturl(), "title:", b.split("<title>")[1].split("</title>")[0] if "<title>" in b else "?")
    except Exception as e: print("fetch", u, "ERR", type(e).__name__, str(e)[:120])
