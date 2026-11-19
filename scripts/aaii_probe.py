"""Probe: can GitHub Actions read the AAII sentiment survey? Prints what each source returns; changes nothing."""
import urllib.request, re
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
      "Accept": "text/html,application/xhtml+xml,application/vnd.ms-excel,*/*", "Accept-Language": "en-US,en;q=0.9"}
for u in ["https://www.aaii.com/files/surveys/sentiment.xls", "https://www.aaii.com/sentimentsurvey/sent_results", "https://www.aaii.com/sentimentsurvey",
          "https://www.aaii.com/sentiment-survey"]:
    try:
        r = urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=30)
        b = r.read(); t = b[:4000].decode("latin-1", "ignore")
        print("OK", r.status, u, len(b), r.headers.get("Content-Type"))
        m = re.findall(r"(Bullish|Neutral|Bearish)[^%]{0,200}?(\d{1,2}\.\d)%", t)
        print("  sample", m[:6], "| incapsula" if "Incapsula" in t or "_Incapsula_" in t else "", t[:200].replace("\n", " "))
    except Exception as e:
        print("FAIL", u, type(e).__name__, str(e)[:120])
