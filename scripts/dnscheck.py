"""Check that the custom domain points to GitHub Pages (used once when connecting the domain)."""
import socket, sys
for h in ["wallstreeter.co.il", "www.wallstreeter.co.il"]:
    try: print(h, sorted({a[4][0] for a in socket.getaddrinfo(h, 80, socket.AF_INET)}))
    except Exception as e: print(h, "ERR", e)
try: print("www cname ->", socket.gethostbyname_ex("www.wallstreeter.co.il")[0:2])
except Exception as e: print("cname ERR", e)
