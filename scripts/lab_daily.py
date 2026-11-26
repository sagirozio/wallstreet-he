"""Daily bars 2015-2021 of the site's stocks + SPY from Alpaca (free plan, SIP history), encrypted for one reader.

The ticker list = the files of the ohlc branch (cloned to the path in argv[1]).
Output lab_daily.enc: gzip(JSON {ticker: {d,o,h,l,c,v}}), AES-256-GCM with a random key wrapped by RSA-OAEP (scripts/lab_pub.pem).
It goes to the orphan branch lab-data (force-pushed), never to main. The log shows counts only. Secrets: ALPACA_KEY_ID, ALPACA_SECRET.
"""
import json, os, sys, time, gzip, base64, pathlib, urllib.request, urllib.parse, urllib.error
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import hashes, serialization

KID, SEC = os.environ.get("ALPACA_KEY_ID", "").strip(), os.environ.get("ALPACA_SECRET", "").strip()
if not KID or not SEC: sys.exit("ALPACA_KEY_ID / ALPACA_SECRET missing")
START, END = os.environ.get("FROM", "2015-01-01"), os.environ.get("TO", "2021-12-31")
ticks = sorted(f.stem for f in pathlib.Path(sys.argv[1]).glob("*.json") if not f.stem.startswith("_"))
print("tickers", len(ticks), START, END, flush=True)

def get(url):
    for k in range(5):
        try:
            r = urllib.request.Request(url, headers={"APCA-API-KEY-ID": KID, "APCA-API-SECRET-KEY": SEC, "Accept": "application/json"})
            with urllib.request.urlopen(r, timeout=30) as f: return json.loads(f.read())
        except urllib.error.HTTPError as e:
            print("http", e.code, e.read()[:200].decode("utf-8", "replace"), flush=True)
            if e.code == 429: time.sleep(30); continue
            if e.code in (401, 403): sys.exit("Alpaca refused the keys")
            return None
        except ValueError:
            sys.exit("bad request header: check the secrets")
        except Exception as e:
            print("err", type(e).__name__, flush=True); time.sleep(5)
    return None

out = {}
for i in range(0, len(ticks), 100):
    grp = ticks[i:i + 100]; amap = {t.replace("-", "."): t for t in grp}
    q = {"symbols": ",".join(amap), "timeframe": "1Day", "start": START, "end": END, "feed": "sip", "adjustment": "split", "limit": "10000"}
    tok = None
    while True:
        if tok: q["page_token"] = tok
        j = get("https://data.alpaca.markets/v2/stocks/bars?" + urllib.parse.urlencode(q))
        if not j: break
        for s, bars in (j.get("bars") or {}).items():
            o = out.setdefault(amap.get(s, s.replace(".", "-")), {"d": [], "o": [], "h": [], "l": [], "c": [], "v": []})
            for b in bars:
                o["d"].append(b["t"][:10]); o["o"].append(b["o"]); o["h"].append(b["h"]); o["l"].append(b["l"]); o["c"].append(b["c"]); o["v"].append(b["v"])
        tok = j.get("next_page_token")
        if not tok: break
        time.sleep(0.35)
    print("groups", i // 100 + 1, "stocks with data", len(out), flush=True)
print("done", len(out), "of", len(ticks), flush=True)

raw = gzip.compress(json.dumps(out, separators=(",", ":")).encode(), 6)
pub = serialization.load_pem_public_key(pathlib.Path("scripts/lab_pub.pem").read_bytes())
key, iv = AESGCM.generate_key(bit_length=256), os.urandom(12)
ct = AESGCM(key).encrypt(iv, raw, None)
wk = pub.encrypt(key, padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None))
pathlib.Path("lab_daily.enc").write_bytes(json.dumps({"v": 1, "gz": 1, "k": base64.b64encode(wk).decode(), "iv": base64.b64encode(iv).decode()}).encode() + b"\n" + ct)
print("wrote lab_daily.enc", round(pathlib.Path("lab_daily.enc").stat().st_size / 1e6, 1), "MB", flush=True)
