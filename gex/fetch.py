"""Download Cboe's delayed-quotes JSON (unofficial, free, no login)."""
import json
import time
import urllib.request

URL = "https://cdn.cboe.com/api/global/delayed_quotes/options/{}.json"
USER_AGENT = "nq-gex-levels/1.0 (personal use; two downloads per run)"


def fetch_json(symbol, tries=3, wait=5.0, opener=urllib.request.urlopen, sleep=time.sleep):
    """symbol is '_NDX' or 'QQQ'. Retries a few times, then raises RuntimeError (the job should fail loudly)."""
    url = URL.format(symbol)
    last = None
    for attempt in range(tries):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with opener(request, timeout=60) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:  # network error, HTTP error, bad JSON: all handled the same way
            last = exc
            if attempt < tries - 1:
                sleep(wait * (attempt + 1))
    raise RuntimeError(f"could not download {url}: {last}")
