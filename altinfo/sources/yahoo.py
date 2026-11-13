"""Daily prices from Yahoo Finance: public chart endpoint, then the yfinance package as a fallback."""
import pandas as pd

from .http import get_json


def _chart(ticker, p1, p2, host):
    js = get_json(f"https://{host}/v8/finance/chart/{ticker}",
                  {"period1": p1, "period2": p2, "interval": "1d", "events": "div,splits"}, tries=2)
    res = js["chart"]["result"][0]
    tz = res.get("meta", {}).get("exchangeTimezoneName", "America/New_York")
    idx = pd.to_datetime(res["timestamp"], unit="s", utc=True).tz_convert(tz).normalize().tz_localize(None)
    adj = (res["indicators"].get("adjclose") or [{}])[0].get("adjclose") or res["indicators"]["quote"][0]["close"]
    return pd.Series(adj, index=idx, name=ticker, dtype=float).dropna()


def prices_many(tickers, start, end):
    """All tickers in one yfinance call (Yahoo rate limits plain requests with HTTP 429).

    Returns a wide DataFrame (date x ticker) or None if yfinance is not installed.
    """
    try:
        import yfinance as yf
    except ImportError:
        return None
    df = yf.download(list(tickers), start=start, end=end, auto_adjust=True, progress=False, threads=True)
    close = df["Close"] if isinstance(df.columns, pd.MultiIndex) else df[["Close"]].rename(columns={"Close": tickers[0]})
    close.index = pd.to_datetime(close.index).tz_localize(None)
    return close


def prices(ticker, start, end):
    """Daily adjusted close (falls back to close). Index: trading date."""
    p1, p2 = int(pd.Timestamp(start, tz="UTC").timestamp()), int(pd.Timestamp(end, tz="UTC").timestamp())
    for host in ("query1.finance.yahoo.com", "query2.finance.yahoo.com"):
        try:
            s = _chart(ticker, p1, p2, host)
            if len(s):
                return s
        except Exception:
            pass
    try:  # yfinance handles Yahoo's cookies and rate limits
        import yfinance as yf
        df = yf.download(ticker, start=start, end=end, auto_adjust=True, progress=False)
        s = df["Close"].squeeze().dropna()
        s.index = pd.to_datetime(s.index).tz_localize(None)
        return s.rename(ticker).astype(float)
    except Exception:
        return pd.Series(dtype=float, name=ticker)


FIELDS = {"forwardPE": "forward_pe", "trailingPE": "trailing_pe", "priceToSalesTrailing12Months": "price_to_sales",
          "enterpriseToEbitda": "ev_to_ebitda", "pegRatio": "peg", "forwardEps": "forward_eps", "trailingEps": "trailing_eps",
          "targetMeanPrice": "target_mean", "targetHighPrice": "target_high", "targetLowPrice": "target_low",
          "numberOfAnalystOpinions": "analysts", "recommendationMean": "recommendation", "marketCap": "market_cap",
          "currentPrice": "price"}


def fundamentals(tickers):
    """Valuation multiples, consensus and price targets (yfinance), annual diluted EPS and monthly prices.

    Returns (snapshot, eps, monthly): snapshot one row per ticker; eps: ticker, period_end, eps;
    monthly: ticker, date, close (6 years, for multiples against history)."""
    try:
        import yfinance as yf
    except ImportError:
        return None, None, None
    snap, eps, mon = [], [], []
    for t in tickers:
        tk = yf.Ticker(t)
        try:
            info = tk.info or {}
            snap.append({"ticker": t, **{v: info.get(k) for k, v in FIELDS.items()}})
        except Exception:
            snap.append({"ticker": t})
        try:
            inc = tk.income_stmt
            if inc is not None and "Diluted EPS" in inc.index:
                for d, v in inc.loc["Diluted EPS"].dropna().items():
                    eps.append({"ticker": t, "period_end": pd.Timestamp(d), "eps": float(v)})
        except Exception:
            pass
        try:
            h = tk.history(period="6y", interval="1mo", auto_adjust=False)["Close"].dropna()
            h.index = pd.to_datetime(h.index).tz_localize(None)
            mon += [{"ticker": t, "date": d, "close": float(v)} for d, v in h.items()]
        except Exception:
            pass
    return pd.DataFrame(snap), pd.DataFrame(eps, columns=["ticker", "period_end", "eps"]), \
        pd.DataFrame(mon, columns=["ticker", "date", "close"])


MONTH_CODES = "FGHJKMNQUVXZ"


def contract_tickers(root, start, n=12, exchange="NYM"):
    """Yahoo tickers of the next n monthly futures contracts, e.g. root BZ -> BZF27.NYM, BZG27.NYM, ..."""
    d = pd.Timestamp(start).to_period("M")
    out = []
    for i in range(1, n + 1):
        m = d + i
        out.append((f"{root}{MONTH_CODES[m.month - 1]}{str(m.year)[-2:]}.{exchange}", m.strftime("%Y-%m")))
    return out
