"""From what the user typed to an asset the engine can analyse: name, price ticker, linked markets, events, places.

1. The curated registry (coverage.py) answers for the names we cover in depth.
2. Anything else is looked up on Yahoo (name, type) and matched to Kalshi and Polymarket by name and ticker.
3. `relevant` throws away markets that only share a word with the asset (a search for gold must not return the
   Golden Globes).
"""
import re

from .coverage import COVERAGE, find
from .errors import InvalidQuery, UnknownAsset

VALID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 .=^&\-]{0,39}$")
# words that reveal a market is about sport, entertainment or politics rather than the asset
NOISE = re.compile(r"golden|medal|globe|grammy|oscar|emmy|album|song|movie|film|olymp|nba|nfl|mlb|nhl|fifa|"
                   r"world cup|gold cup|championship|playoff|touchdown|season|episode|actor|actress", re.I)
PRICE_WORDS = re.compile(r"price|close|settle|hit|dip|above|below|reach|\$|futures|per (?:oz|bbl|lb|bushel)|usd/", re.I)
# names for tickers we hold prices for, used when Yahoo cannot be reached
KNOWN = {"AMD": "Advanced Micro Devices", "TSM": "TSMC", "MU": "Micron", "AVGO": "Broadcom", "QCOM": "Qualcomm",
         "INTC": "Intel", "FCX": "Freeport-McMoRan", "SCCO": "Southern Copper", "TECK": "Teck Resources",
         "NEM": "Newmont", "DE": "Deere", "ADM": "Archer-Daniels-Midland", "BG": "Bunge", "CTVA": "Corteva",
         "SBUX": "Starbucks", "SPY": "S&P 500 ETF", "QQQ": "Nasdaq 100 ETF", "XLE": "Energy Select Sector ETF",
         "GLD": "SPDR Gold Shares", "SMH": "VanEck Semiconductor ETF", "NG=F": "Natural gas", "BTC-USD": "Bitcoin"}
SUFFIXES = re.compile(r",?\s+(inc|corp|corporation|company|co|ltd|plc|sa|nv|ag|holdings|group|limited|class [ab])\.?$", re.I)


def clean_name(name):
    """'NVIDIA Corporation' -> 'NVIDIA': the word people use in market questions."""
    n = name.strip()
    for _ in range(3):
        n = SUFFIXES.sub("", n).strip()
    return n


def relevant(text, asset):
    """Does this market title really concern the asset? Whole word match on the name or the ticker, no noise words,
    and for commodities a price context (so 'gold' alone is not enough)."""
    t = str(text)
    if NOISE.search(t):
        return False
    tk = re.escape(asset["ticker_label"])
    name = re.escape(asset["short_name"])
    hit_name = re.search(rf"\b{name}\b", t, re.I) is not None
    hit_tk = re.search(rf"\({tk}\)|\b{tk}\b", t) is not None and len(asset["ticker_label"]) >= 3
    if not (hit_name or hit_tk):
        return asset.get("pattern") is not None and re.search(asset["pattern"], t, re.I) is not None and asset["in_registry"]
    if asset["kind"] == "commodity" and not asset["in_registry"]:
        return PRICE_WORDS.search(t) is not None
    return True


NEWS = {"BRENT": '("Brent crude" OR "oil prices" OR "oil price")', "WTI": '("WTI crude" OR "oil prices" OR "oil price")',
        "GOLD": '("gold price" OR "gold prices")'}


def search_terms(a):
    """The words used to look the asset up on Kalshi, Polymarket and in the news."""
    words = [a["short_name"]]
    if a["kind"] == "company":
        words.append(a["ticker_label"])
    for alt in (a.get("pattern") or "").split("|"):   # plain words of the registry pattern, e.g. Hormuz, Iran
        w = alt.replace("\\b", "").strip()
        if re.fullmatch(r"[A-Za-z][A-Za-z ]{2,30}", w):
            words.append(w)
    seen, uniq = set(), []
    for w in words:
        if w and w.lower() not in seen:
            seen.add(w.lower())
            uniq.append(w)
    words, n, tk = uniq, a["short_name"], a["ticker_label"]
    if a["key"] in NEWS:
        news = NEWS[a["key"]]
    elif a["kind"] == "company":
        name = f'"{n}"' if " " in n else n
        news = f"({name} OR {tk})" if tk.isalpha() and len(tk) >= 3 and tk.lower() != n.lower() else name
    else:
        news = f'("{n.lower()} price" OR "{n.lower()} prices")'

    return {"kalshi": words, "poly": words, "news": news}


def resolve(query, fetcher):
    """Return the asset description used by every later step. Raises InvalidQuery or UnknownAsset."""
    q = (query or "").strip()
    if not VALID.match(q):
        raise InvalidQuery("Type a ticker such as NVDA or a commodity such as copper.",
                           "Letters, digits, spaces and . = ^ & - only, up to 40 characters.")
    key = find(q)
    if key:
        c = COVERAGE[key]
        return {"key": key, "query": q, "name": c["name"], "short_name": c["name"].replace(" crude", ""), "kind": c["kind"],
                "group": c["group"], "region": c.get("region", ""), "price_ticker": c["price"],
                "ticker_label": key if c["kind"] == "company" else c["price"], "linked": c["linked"],
                "kalshi_series": list(c["kalshi"]), "kalshi_pattern": c.get("kalshi_pattern"), "pattern": c["polymarket"],
                "poly_query": c["name"].replace(" crude", ""), "events": c["events"], "signals": c["signals"],
                "sites": c["sites"], "curve": c.get("curve"), "in_registry": True}
    tk = q.upper().replace(" ", "")
    prof = fetcher.profile(tk)
    px = fetcher.prices(tk)
    if prof is None and px.empty:
        raise UnknownAsset(f"We could not find anything for “{q}”.",
                           "Check the ticker (for example AAPL, TSM, GC=F) or try one of the covered names.")
    name = (prof or {}).get("name") or KNOWN.get(tk, tk)
    typ = ((prof or {}).get("type") or "").upper()
    kind = "commodity" if typ == "FUTURE" or tk.endswith("=F") else "company" if typ in ("EQUITY", "") else typ.lower()
    short = clean_name(name)
    return {"key": tk, "query": q, "name": name, "short_name": short, "kind": kind,
            "group": (prof or {}).get("sector") or ("Commodity" if kind == "commodity" else "Equity"),
            "region": (prof or {}).get("country") or "", "price_ticker": tk, "ticker_label": tk, "linked": [],
            "kalshi_series": [], "kalshi_pattern": rf"\b{re.escape(short)}\b",
            "pattern": rf"\b{re.escape(short)}\b|\({re.escape(tk)}\)", "poly_query": short, "events": [], "signals": [],
            "sites": [], "curve": None, "in_registry": False}
