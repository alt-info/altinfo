"""News attention from the GDELT DOC 2.0 API (free, no key): https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/

GDELT reads news sites worldwide in many languages. For a query it returns:
  volume     share of all monitored articles that mention it, by day ("Volume Intensity")
  tone       average tone of those articles, by day (below 0 negative, above 0 positive)
  articles   the most relevant recent headlines
GDELT asks for at most one request every 5 seconds, so calls are spaced by a lock.
"""
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

import pandas as pd

from .http import HEADERS, LAST_ERROR

URL = "https://api.gdeltproject.org/api/v2/doc/doc"
URL_PLAIN = "http://api.gdeltproject.org/api/v2/doc/doc"   # GDELT's https handshake is often slow; the data is public
_lock, _last = threading.Lock(), [0.0]
_url = [URL]
LAST_RAW = {}   # first characters of the last answer per mode, for diagnosis
SPACING = 8.0


def _get(url, params, timeout):
    """Raw GET: GDELT answers its rate limit with plain text, not JSON, so the text is read first."""
    q = urllib.parse.urlencode(params)
    req = urllib.request.Request(f"{url}?{q}", headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def _call(query, mode, **extra):
    """One GDELT request, spaced from the previous one; retried when GDELT says 'Please limit requests'."""
    params = {"query": query, "mode": mode, "format": "json", **extra}
    err = None
    with _lock:  # one request at a time across every analysis running
        for attempt in range(3):
            wait = _last[0] + SPACING - time.time()
            if wait > 0:
                time.sleep(wait)
            url = _url[0]
            try:
                txt = _get(url, params, 10 if url == URL else 30)
            except urllib.error.HTTPError as e:
                _last[0] = time.time()
                if e.code == 429:            # too many requests: give up at once, the caller falls back to headlines
                    err = "HTTP 429 rate limit"
                    break
                err = f"HTTP {e.code}"
                break
            except Exception as e:  # https handshake too slow on some networks: switch to the plain address for good
                err = f"{type(e).__name__}: {e}"[:160]
                _last[0] = time.time()
                if url == URL:
                    _url[0] = URL_PLAIN
                continue
            _last[0] = time.time()
            LAST_RAW[mode] = txt[:600]
            if txt.lstrip().startswith("{"):
                LAST_ERROR.pop("api.gdeltproject.org", None)
                try:
                    return json.loads(txt, strict=False)   # GDELT sometimes leaves control characters in titles
                except ValueError as e:
                    err = f"unreadable answer: {e}"[:160]
                    break
            if "limit requests" in txt.lower():   # rate limited: one more try after the pause, then give up
                err = "GDELT rate limit 429"
                if attempt >= 1:
                    break
                continue
            err = txt.strip()[:160] or "empty answer"
            break
    LAST_ERROR["api.gdeltproject.org"] = err
    return {}


def _timeline(js):
    tl = (js.get("timeline") or [{}])[0].get("data") or []
    def day(x):
        t = pd.Timestamp(x)
        return (t.tz_convert(None) if t.tzinfo else t).normalize()
    s = pd.Series({day(p["date"]): float(p["value"]) for p in tl if "date" in p and "value" in p}, dtype=float)
    return s.groupby(s.index.normalize()).mean().sort_index() if len(s) else s


def volume(query, timespan="3months"):
    return _timeline(_call(query, "timelinevol", timespan=timespan))


def tone(query, timespan="3months"):
    return _timeline(_call(query, "timelinetone", timespan=timespan))


def articles(query, n=8, timespan="7days"):
    js = _call(query, "artlist", maxrecords=max(n * 3, 20), timespan=timespan, sort="hybridrel")
    out, seen = [], set()
    for a in js.get("articles") or []:
        t = (a.get("title") or "").strip()
        if not t or t.lower() in seen or (a.get("language") and a["language"] != "English"):
            continue
        seen.add(t.lower())
        out.append({"title": t, "url": a.get("url"), "domain": a.get("domain"), "seen": (a.get("seendate") or "")[:8]})
        if len(out) >= n:
            break
    return out


if __name__ == "__main__":   # diagnosis: python -m altinfo.sources.gdelt   (about one minute)
    import sys
    q = " ".join(a for a in sys.argv[1:]) or "apple"
    tests = [("timelinevol", {}), ("timelinevol", {"timespan": "3m"}), ("timelinevol", {"timespan": "12w"}),
             ("timelinevol", {"timespan": "90d"}), ("artlist", {"maxrecords": 5}), ("artlist", {"maxrecords": 5, "timespan": "7d"})]
    for mode, extra in tests:
        params = {"query": q, "mode": mode, "format": "json", **extra}
        for url in (URL_PLAIN,):
            try:
                txt = _get(url, params, 30)
                print(f"{mode:12} {str(extra):30} -> {len(txt):6} chars: {txt[:140]!r}")
            except Exception as e:
                print(f"{mode:12} {str(extra):30} -> {type(e).__name__}: {e}")
        time.sleep(SPACING)
