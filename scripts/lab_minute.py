"""5-minute bars of the lab's breakout days, from Alpaca (free plan, SIP history), encrypted for one reader.

lab_req.json  = [[ticker, "YYYY-MM-DD"], ...]  (the days to fetch)
lab_min.enc   = the bars, encrypted: AES-256-GCM with a random key, the key wrapped with RSA-OAEP (scripts/lab_pub.pem).
                Only the holder of the matching private key (kept outside this repo) can read it.
The log shows counts only. Secrets: ALPACA_KEY_ID, ALPACA_SECRET.
"""
import json, os, sys, time, base64, pathlib, urllib.request, urllib.parse, urllib.error
from collections import defaultdict
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import hashes, serialization

KID, SEC = os.environ.get("ALPACA_KEY_ID", ""), os.environ.get("ALPACA_SECRET", "")
if not KID or not SEC: sys.exit("ALPACA_KEY_ID / ALPACA_SECRET missing")
req = json.loads(pathlib.Path("lab_req.json").read_text())
by_day = defaultdict(list)
for t, d in req: by_day[d].append(t)
print("days", len(by_day), "requests", len(req))

def get(url):
    for k in range(5):
        try:
            r = urllib.request.Request(url, headers={"APCA-API-KEY-ID": KID, "APCA-API-SECRET-KEY": SEC, "Accept": "application/json"})
            with urllib.request.urlopen(r, timeout=40) as f: return json.loads(f.read())
        except urllib.error.HTTPError as e:
            print("http", e.code)
            if e.code == 429: time.sleep(30); continue
            if e.code in (401, 403): sys.exit("Alpaca refused the keys (check the two secrets)")
            time.sleep(5)
        except Exception as e:
            print("err", type(e).__name__); time.sleep(5)
    return None

out, n_ok = {}, 0
for d, syms in sorted(by_day.items()):
    q = {"symbols": ",".join(sorted(set(syms))), "timeframe": "5Min", "start": f"{d}T13:00:00Z", "end": f"{d}T21:00:00Z",
         "feed": "sip", "adjustment": "split", "limit": "10000"}
    tok = None
    while True:
        if tok: q["page_token"] = tok
        j = get("https://data.alpaca.markets/v2/stocks/bars?" + urllib.parse.urlencode(q))
        if not j: break
        for s, bars in (j.get("bars") or {}).items():
            out.setdefault(f"{s}_{d}", []).extend([[b["t"], b["o"], b["h"], b["l"], b["c"], b["v"]] for b in bars])
        tok = j.get("next_page_token")
        if not tok: break
    time.sleep(0.35)        # well under 200 requests a minute
n_ok = len(out)
print("bars for", n_ok, "of", len(req))

pub = serialization.load_pem_public_key(pathlib.Path("scripts/lab_pub.pem").read_bytes())
key, iv = AESGCM.generate_key(bit_length=256), os.urandom(12)
ct = AESGCM(key).encrypt(iv, json.dumps(out, separators=(",", ":")).encode(), None)
wk = pub.encrypt(key, padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None))
b64 = lambda x: base64.b64encode(x).decode()
pathlib.Path("lab_min.enc").write_text(json.dumps({"v": 1, "k": b64(wk), "iv": b64(iv), "ct": b64(ct)}))
print("wrote lab_min.enc", round(pathlib.Path("lab_min.enc").stat().st_size / 1e3), "KB")
