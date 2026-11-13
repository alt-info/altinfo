"""Normalisation: every source speaks its own dialect, the engine wants one.

contracts   Kalshi and Polymarket rows -> one schema:
            venue, id, title, contract, prob (0 to 1), volume, closes (date), kind, level, quality
            kind is one of price_above, touch_high, touch_low, earnings_beat, mention, data_release, event
series      any time series -> [{"t": "YYYY-MM-DD", "v": float}], sorted, no gaps filled
"""
import re

import pandas as pd

KINDS = ("price_above", "touch_high", "touch_low", "earnings_beat", "mention", "data_release", "event")
_num = r"\$?\s*([\d,]+(?:\.\d+)?)"


def _level(text):
    m = re.search(_num, text.replace(",", ""))
    return float(m.group(1)) if m else None


def _kind_kalshi(title, strike):
    t = title.lower()
    if "say during" in t or "mention" in t:
        return "mention"
    if strike == strike and strike is not None:
        if re.search(r"maximum .* (reach|be above)|\bhigh\b", t):
            return "touch_high"
        if re.search(r"minimum .* (reach|be below)|\blow\b", t):
            return "touch_low"
        if re.search(r"close price|settle|settlement price|closing price", t):
            return "price_above"
        if re.search(r"inventor|report|employees|revenue|cpi|rate", t):
            return "data_release"
    return "event"


def _kind_poly(q):
    t = q.lower()
    if re.search(r"beat .*earnings|earnings beat|eps above", t):
        return "earnings_beat"
    if re.search(r"close above|closes above|finish above|settle above", t):
        return "price_above"
    if re.search(r"hit \(high\)|\bhit \$|reach \$|touch \$", t):
        return "touch_high"
    if re.search(r"dip to|\(low\)|fall to|drop to", t):
        return "touch_low"
    if re.search(r"\bsay\b|mention", t):
        return "mention"
    return "event"


def _quality(volume, spread):
    """high / medium / low: is this price backed by trading, and is the bid ask spread tight?"""
    if volume is None or volume != volume or volume <= 0:
        return "low"
    if spread is not None and spread == spread and spread > 0.10:
        return "low"
    return "high" if volume >= 5000 else "medium"


def _numeric(df, cols):
    """The live APIs send prices and volumes as text ("0.4500"); saved files hold numbers. Make both numbers."""
    df = df.copy()
    for c in cols:
        if c in df:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def kalshi_contracts(df):
    df = _numeric(df, ["yes_bid_dollars", "yes_ask_dollars", "last_price_dollars", "volume_fp", "open_interest_fp",
                       "floor_strike", "cap_strike"])
    rows = []
    for r in df.itertuples():
        bid, ask, last = getattr(r, "yes_bid_dollars", None), getattr(r, "yes_ask_dollars", None), getattr(r, "last_price_dollars", None)
        tight = bid == bid and ask == ask and ask is not None and ask > 0 and (ask - bid) <= 0.10
        prob = (bid + ask) / 2 if tight else last
        strike = getattr(r, "floor_strike", None)
        vol = getattr(r, "volume_fp", 0) or 0
        if prob is None or prob != prob:
            continue
        if (vol != vol or vol <= 0) and not tight:   # never traded and no tight quote: the price is a placeholder
            continue
        rows.append({"venue": "Kalshi", "id": r.ticker, "title": r.title, "contract": getattr(r, "yes_sub_title", "") or "",
                     "prob": float(prob), "volume": float(vol if vol == vol else 0),
                     "closes": str(getattr(r, "close_time", ""))[:10], "kind": _kind_kalshi(str(r.title), strike),
                     "level": float(strike) if strike == strike and strike is not None else None,
                     "quality": _quality(vol, (ask - bid) if ask == ask and bid == bid else None),
                     "series": getattr(r, "series", ""), "token": None})
    return rows


def poly_contracts(df):
    df = _numeric(df, ["price", "volume", "liquidity"])
    rows = []
    for r in df.itertuples():
        if r.price is None or r.price != r.price:
            continue
        k = _kind_poly(str(r.question))
        rows.append({"venue": "Polymarket", "id": r.market_slug, "title": r.question, "contract": "Yes", "prob": float(r.price),
                     "volume": float(r.volume or 0), "closes": str(r.end)[:10], "kind": k,
                     "level": _level(str(r.question).split("$", 1)[1]) if "$" in str(r.question) and k != "event" else None,
                     "quality": _quality(r.volume, None), "series": getattr(r, "event_slug", ""),
                     "token": getattr(r, "yes_token", None)})
    return rows


def series(s, digits=4):
    """pandas Series (date index) -> list of points for the API."""
    if s is None or len(s) == 0:
        return []
    s = s.dropna().sort_index()
    return [{"t": pd.Timestamp(d).strftime("%Y-%m-%d"), "v": round(float(v), digits)} for d, v in s.items()]
