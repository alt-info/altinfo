"""Kalshi Trade API v2 (public, read only, no key needed).

Docs: https://docs.kalshi.com . Live data for open and recent markets; settled markets older
than the cutoff live under /historical. Daily candles close at midnight US Eastern time.
"""
from datetime import datetime, timezone

import pandas as pd

from .http import get_json

BASE = "https://api.elections.kalshi.com/trade-api/v2"


def _close(d):
    d = d or {}
    v = d.get("close_dollars", d.get("close"))
    return None if v is None else float(v)


def candle_price(c, max_spread=0.10):
    """Bid/ask midpoint when the spread is tight, otherwise the last trade."""
    b, a, p = _close(c.get("yes_bid")), _close(c.get("yes_ask")), _close(c.get("price"))
    if b is not None and a is not None and 0 < a and b <= a and a - b <= max_spread:
        return (a + b) / 2
    return p


def _ts(dt):
    return int(pd.Timestamp(dt, tz="UTC").timestamp())


def candles(tickers, start, end, period=1440, archive=True):
    """Daily candles for several markets: tidy DataFrame (date, ticker, price, volume, open_interest).

    Uses the batch endpoint for live markets and falls back to the historical archive.
    `date` is the US Eastern trading day the candle covers.
    """
    s, e = _ts(start), _ts(end)
    got = {}
    for i in range(0, len(tickers), 5):  # small batches: the endpoint caps the number of candles per call
        chunk = tickers[i:i + 5]
        js = get_json(f"{BASE}/markets/candlesticks",
                      {"market_tickers": ",".join(chunk), "start_ts": s, "end_ts": e, "period_interval": period})
        for mk in (js or {}).get("markets", []):
            got[mk.get("market_ticker") or mk.get("ticker")] = mk.get("candlesticks", [])
    for t in tickers:  # one market at a time on the live endpoint, then the historical archive
        if got.get(t):
            continue
        js = get_json(f"{BASE}/series/{t.split('-')[0]}/markets/{t}/candlesticks",
                      {"start_ts": s, "end_ts": e, "period_interval": period}, tries=1)
        got[t] = (js or {}).get("candlesticks", [])
        if got[t] or not archive:
            continue
        js = get_json(f"{BASE}/historical/markets/{t}/candlesticks",
                      {"start_ts": s, "end_ts": e, "period_interval": period})
        got[t] = (js or {}).get("candlesticks", [])
    rows = []
    for t, cs in got.items():
        for c in cs:
            day = datetime.fromtimestamp(int(c["end_period_ts"]) - 6 * 3600, tz=timezone.utc).date()
            rows.append({"date": pd.Timestamp(day), "ticker": t, "price": candle_price(c),
                         "volume": float(c.get("volume_fp", c.get("volume", 0)) or 0),
                         "open_interest": float(c.get("open_interest_fp", c.get("open_interest", 0)) or 0)})
    return pd.DataFrame(rows, columns=["date", "ticker", "price", "volume", "open_interest"])


def all_series(category=None):
    js = get_json(f"{BASE}/series", {"category": category} if category else None)
    return pd.DataFrame((js or {}).get("series", []))


def find_series(keywords, categories=("Economics", "Commodities", "Financials", "Companies", "World", "Politics")):
    """Series whose title or ticker contains any keyword (case insensitive)."""
    frames = [all_series(c) for c in categories] + [all_series()]
    df = pd.concat([f for f in frames if len(f)], ignore_index=True).drop_duplicates("ticker") if any(
        len(f) for f in frames) else pd.DataFrame(columns=["ticker", "title"])
    if df.empty:
        return df
    text = (df["title"].fillna("") + " " + df["ticker"].fillna("")).str.lower()
    mask = pd.Series(False, index=df.index)
    for k in keywords:
        mask |= text.str.contains(k.lower(), regex=False)
    return df[mask][["ticker", "title"] + [c for c in ["category", "frequency"] if c in df]]


def markets(series_ticker=None, event_ticker=None, status=None, limit=1000):
    """Market snapshot (one row per contract) for a series or an event, following the cursor."""
    params = {"limit": limit}
    if series_ticker:
        params["series_ticker"] = series_ticker
    if event_ticker:
        params["event_ticker"] = event_ticker
    if status:
        params["status"] = status
    rows, cursor = [], None
    for _ in range(20):
        if cursor:
            params["cursor"] = cursor
        js = get_json(f"{BASE}/markets", params) or {}
        rows += js.get("markets", [])
        cursor = js.get("cursor")
        if not cursor:
            break
    keep = ["ticker", "event_ticker", "title", "yes_sub_title", "status", "result", "open_time", "close_time",
            "last_price_dollars", "yes_bid_dollars", "yes_ask_dollars", "volume_fp", "open_interest_fp",
            "floor_strike", "cap_strike", "strike_type"]
    df = pd.DataFrame(rows)
    return df[[c for c in keep if c in df]] if len(df) else df
