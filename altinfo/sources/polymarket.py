"""Polymarket public APIs (read only, no key needed).

Gamma API: market discovery and metadata. CLOB API: price history of each outcome token.
Polymarket blocks trading from the UK and parts of the EU; reading public data is not trading.
"""
import json

import pandas as pd

from .http import get_json

GAMMA, CLOB = "https://gamma-api.polymarket.com", "https://clob.polymarket.com"


def _tokens(m):
    t = m.get("clobTokenIds")
    return json.loads(t) if isinstance(t, str) else (t or [])


def _outcomes(m):
    o = m.get("outcomes")
    return json.loads(o) if isinstance(o, str) else (o or [])


def event(slug):
    js = get_json(f"{GAMMA}/events", {"slug": slug})
    return js[0] if js else None


def search(query, closed=False, limit=50):
    """Events matching a free text query. Tries /public-search, then scans open events by title."""
    js = get_json(f"{GAMMA}/public-search", {"q": query, "limit_per_type": limit, "events_status": "active"})
    evs = (js or {}).get("events") or []
    if not evs:
        evs, words = [], [w.lower() for w in query.split()]
        for off in range(0, 3000, 500):
            page = get_json(f"{GAMMA}/events", {"closed": str(closed).lower(), "limit": 500, "offset": off,
                                                "order": "volume", "ascending": "false"}) or []
            evs += [e for e in page if all(w in (e.get("title", "") + " " + e.get("slug", "")).lower() for w in words)]
            if len(page) < 500:
                break
    return evs


def markets_table(events):
    """One row per market (the Yes token) with question, price, volume, liquidity and end date."""
    rows = []
    for e in events:
        for m in e.get("markets", []):
            tok, out = _tokens(m), _outcomes(m)
            prices = m.get("outcomePrices")
            prices = json.loads(prices) if isinstance(prices, str) else (prices or [])
            rows.append({"event_slug": e.get("slug"), "event_title": e.get("title"), "market_slug": m.get("slug"),
                         "question": m.get("question"), "group_item": m.get("groupItemTitle"),
                         "yes_token": tok[0] if tok else None, "outcome0": out[0] if out else None,
                         "price": float(prices[0]) if prices else None, "volume": float(m.get("volume") or 0),
                         "liquidity": float(m.get("liquidity") or 0), "end": m.get("endDate"),
                         "closed": m.get("closed")})
    return pd.DataFrame(rows)


def history(token, start_ts=None, end_ts=None, fidelity=1440):
    """Price history of an outcome token: DataFrame (time, prob). Daily by default."""
    js = get_json(f"{CLOB}/prices-history", {"market": token, "interval": "max", "fidelity": fidelity})
    pts = (js or {}).get("history", [])
    if not pts and start_ts:
        js = get_json(f"{CLOB}/prices-history", {"market": token, "startTs": start_ts, "endTs": end_ts,
                                                  "fidelity": fidelity})
        pts = (js or {}).get("history", [])
    df = pd.DataFrame(pts)
    if df.empty:
        return pd.DataFrame(columns=["time", "prob"])
    df["time"] = pd.to_datetime(df["t"], unit="s", utc=True)
    return df.rename(columns={"p": "prob"})[["time", "prob"]]


def daily_close(hist):
    """Last price of each US Eastern trading day."""
    if hist.empty:
        return pd.Series(dtype=float)
    et = hist.set_index(hist["time"].dt.tz_convert("America/New_York"))["prob"]
    s = et.groupby(et.index.date).last()
    s.index = pd.to_datetime(s.index)
    return s
