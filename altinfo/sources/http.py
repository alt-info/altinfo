"""Minimal HTTP helper: standard library only, retries, browser like headers."""
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "application/json,text/plain,*/*",
}


LAST_ERROR = {}
FAILS = [0]          # number of failed calls so far: lets callers tell "no data" from "site unreachable"
RETRY_PAUSE = 2.0    # seconds, multiplied by the attempt number; the web app lowers it to stay responsive
TIMEOUT = 30
MAX_TRIES = None     # the web app caps retries so a blocked site cannot keep the user waiting for minutes
_reported = set()


def _report(url, err):
    host = urllib.parse.urlparse(url).netloc
    LAST_ERROR[host] = err
    FAILS[0] += 1
    if host not in _reported:  # print the first failure for each site, so problems are visible
        _reported.add(host)
        print(f"  ! {host}: {err}", file=sys.stderr)


def get_json(url, params=None, tries=3, pause=0.25, timeout=None):
    """GET a JSON document. Returns None on 400/404 or after `tries` failures."""
    if params:
        url = f"{url}?{urllib.parse.urlencode(params, safe=',')}"
    err = None
    for i in range(min(tries, MAX_TRIES or tries)):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=timeout or TIMEOUT) as r:
                out = json.loads(r.read().decode("utf-8"))
            time.sleep(pause)
            return out
        except urllib.error.HTTPError as e:
            err = f"HTTP {e.code} {e.reason}"
            if e.code in (400, 404):
                return None
            time.sleep(RETRY_PAUSE * (i + 1))
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
            if "CERTIFICATE_VERIFY_FAILED" in str(e):
                break  # retrying will not help
            time.sleep(RETRY_PAUSE * (i + 1))
    _report(url, err)
    return None
