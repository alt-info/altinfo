"""Recent headlines when GDELT is not available: Google News search feed (RSS) and Yahoo Finance news. Free, no key.

google_news   up to about 100 headlines for a query over the last `days` days, with source and time
yahoo_news    the latest headlines Yahoo Finance attaches to a ticker (also works for futures such as GC=F)
tone          a simple headline tone from a small finance word list: share of positive minus negative words
"""
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

import pandas as pd

from .http import HEADERS, _report

GOOGLE = "https://news.google.com/rss/search"

POS = {"beat", "beats", "surge", "surges", "soar", "soars", "rally", "rallies", "gain", "gains", "record", "upgrade",
       "upgrades", "strong", "stronger", "rise", "rises", "jump", "jumps", "growth", "bullish", "higher", "profit", "tops",
       "outperform", "boost", "boosts", "rebound", "rebounds", "climb", "climbs", "optimism", "deal", "approval", "wins"}
NEG = {"miss", "misses", "fall", "falls", "drop", "drops", "plunge", "plunges", "slump", "slumps", "cut", "cuts",
       "downgrade", "downgrades", "weak", "weaker", "loss", "losses", "lawsuit", "probe", "ban", "tariff", "tariffs",
       "decline", "declines", "bearish", "lower", "warning", "warns", "fears", "fear", "selloff", "sell-off", "crash",
       "slide", "slides", "sink", "sinks", "tumble", "tumbles", "risk", "risks", "shortage", "disruption", "strike", "halt"}


def _get_text(url, timeout=20):
    req = urllib.request.Request(url, headers=HEADERS | {"Accept": "application/rss+xml,application/xml,text/xml,*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def parse_rss(xml):
    """Google News RSS -> list of headlines (title, url, source, time)."""
    out = []
    root = ET.fromstring(xml)
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        src = (it.findtext("source") or "").strip()
        if src and title.endswith(" - " + src):
            title = title[: -len(src) - 3].strip()
        try:
            t = pd.Timestamp(parsedate_to_datetime(it.findtext("pubDate") or "")).tz_convert("UTC").tz_localize(None)
        except Exception:
            t = None
        if title:
            out.append({"title": title, "url": (it.findtext("link") or "").strip(), "domain": src, "time": t})
    return out


def google_news(query, days=7):
    q = f"{query} when:{days}d"
    url = f"{GOOGLE}?{urllib.parse.urlencode({'q': q, 'hl': 'en-GB', 'gl': 'GB', 'ceid': 'GB:en'})}"
    try:
        return parse_rss(_get_text(url))
    except Exception as e:
        _report(url, f"{type(e).__name__}: {e}"[:160])
        return []


def yahoo_news(ticker):
    try:
        import yfinance as yf
        items = yf.Ticker(ticker).news or []
    except Exception:
        return []
    out = []
    for n in items:
        c = n.get("content") or n          # newer yfinance nests the article under "content"
        title = c.get("title")
        url = (c.get("canonicalUrl") or {}).get("url") or c.get("link")
        src = (c.get("provider") or {}).get("displayName") or c.get("publisher") or "Yahoo Finance"
        ts = c.get("pubDate") or c.get("providerPublishTime")
        try:
            t = pd.Timestamp(ts, unit="s") if isinstance(ts, (int, float)) else pd.Timestamp(ts).tz_convert("UTC").tz_localize(None)
        except Exception:
            t = None
        if title:
            out.append({"title": title, "url": url, "domain": src, "time": t})
    return out


def tone(titles):
    """Headline tone between -1 (all negative words) and +1 (all positive), and how many headlines carried a signal."""
    pos = neg = hit = 0
    for t in titles:
        words = set(re.findall(r"[a-z][a-z\-]+", t.lower()))
        p, n = len(words & POS), len(words & NEG)
        pos, neg = pos + p, neg + n
        hit += 1 if p or n else 0
    return ((pos - neg) / (pos + neg) if pos + neg else 0.0), hit
