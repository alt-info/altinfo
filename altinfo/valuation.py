"""Valuation check of the reports: is a good result enough to move the price?

runup          share price change before the release (1 week, 1 month, 3 months)
multiples      multiples, consensus and price targets of a company against its peers
pe_history     trailing P/E through time (monthly price / last annual EPS already reported)
curve_spread   commodities: gap between the near and later futures contracts (backwardation or contango)
"""
import pandas as pd


def runup(prices: pd.Series, asof=None, windows=(5, 21, 63)):
    """Return over the last 5, 21 and 63 trading days up to `asof`."""
    p = prices.dropna()
    if asof is not None:
        p = p.loc[:pd.Timestamp(asof)]
    names = {5: "1 week", 21: "1 month", 63: "3 months"}
    return pd.Series({names.get(w, f"{w} days"): p.iloc[-1] / p.iloc[-1 - w] - 1 for w in windows if len(p) > w})


def multiples(fund: pd.DataFrame, company, peers):
    """One row per company, with the peer median and the company's premium to it."""
    cols = ["forward_pe", "trailing_pe", "price_to_sales", "ev_to_ebitda", "peg"]
    f = fund.set_index("ticker").reindex([company] + list(peers))
    t = f[[c for c in cols if c in f]].astype(float)
    med = t.loc[[p for p in peers if p in t.index]].median()
    t.loc["Peer median"] = med
    t.loc[f"{company} vs peers"] = t.loc[company] / med - 1
    t.index.name = None
    return t


def consensus(fund: pd.DataFrame, company):
    """Analyst consensus and price targets for one company, formatted for display."""
    r = fund.set_index("ticker").loc[company]
    ok = lambda v: v is not None and v == v  # noqa: E731
    f = lambda k, fmt: fmt.format(r[k]) if k in r and ok(r[k]) else None  # noqa: E731
    out = {"Analysts": f("analysts", "{:.0f}"), "Recommendation (1 buy, 5 sell)": f("recommendation", "{:.1f}"),
           "Forward EPS": f("forward_eps", "${:.2f}"), "Target, low": f("target_low", "${:,.0f}"),
           "Target, mean": f("target_mean", "${:,.0f}"), "Target, high": f("target_high", "${:,.0f}")}
    if ok(r.get("price")) and ok(r.get("target_mean")):
        out["Upside to mean target"] = f"{r['target_mean'] / r['price'] - 1:+.0%}"
    return pd.Series({k: v for k, v in out.items() if v is not None})


def pe_history(monthly: pd.DataFrame, eps: pd.DataFrame, ticker, lag_days=60):
    """Trailing P/E each month: price divided by the last fiscal year EPS published at that date
    (fiscal year end plus `lag_days` for the 10-K). Approximate: annual EPS changes once a year."""
    m = monthly[monthly.ticker == ticker].copy()
    e = eps[eps.ticker == ticker].copy()
    if m.empty or e.empty:
        return pd.Series(dtype=float)
    m["date"] = pd.to_datetime(m["date"])
    e["known"] = pd.to_datetime(e["period_end"]) + pd.Timedelta(days=lag_days)
    m = pd.merge_asof(m.sort_values("date"), e.sort_values("known")[["known", "eps"]], left_on="date", right_on="known")
    m = m.dropna(subset=["eps"])
    m = m[m.eps > 0]
    return pd.Series((m["close"] / m["eps"]).values, index=m["date"].values, name=f"{ticker} trailing P/E")


def curve_spread(curve: pd.DataFrame, root, near=1, far=6):
    """Daily spread between the near and the far contract of a futures curve ($ per unit).

    Positive (near above far) is backwardation: the market pays more for barrels now, a sign of tight supply."""
    c = curve[curve.root == root].copy()
    if c.empty:
        return pd.DataFrame()
    months = sorted(c["month"].unique())
    if len(months) < far:
        far = len(months)
    w = c.pivot_table(index="date", columns="month", values="close").sort_index()
    out = pd.DataFrame({"near": w[months[near - 1]], "far": w[months[far - 1]]})
    out["spread"] = out["near"] - out["far"]
    out.attrs["near_month"], out.attrs["far_month"] = months[near - 1], months[far - 1]
    return out.dropna()


def latest_curve(curve: pd.DataFrame, root):
    """The whole curve on the last available day: month, close."""
    c = curve[curve.root == root]
    if c.empty:
        return pd.Series(dtype=float)
    last = c[c.date == c.date.max()]
    return last.set_index("month")["close"].sort_index()
