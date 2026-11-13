"""eventbeta: price portfolio exposure to real world events with prediction market odds.

Minimal prototype of the EventBeta Python library. Pure numpy and pandas.

Main functions
  fed_expected_move   Kalshi Fed decision markets -> expected move at the next FOMC (bp)
  event_changes       daily changes of event probabilities (percentage points)
  asset_returns       daily asset returns (%); level changes for VIX and yields
  ols_hac             OLS with Newey West standard errors
  event_betas         event beta of every asset to every event
  portfolio_exposure  portfolio event betas and scenario P&L
  hedge_ratio         size of a hedge that neutralises one event exposure
"""
from __future__ import annotations

import numpy as np
import pandas as pd

OUTCOME_BP = {"C26": -50, "C25": -25, "H0": 0, "H25": 25, "H26": 50}
LEVEL_SERIES = {"^VIX": 1.0, "^TNX": 100.0, "^IRX": 100.0}  # change in points or bp


# --------------------------------------------------------------------------- data


def _on_calendar(s: pd.Series, calendar) -> pd.Series:
    """Value at each trading day (last observation, at most 3 days old)."""
    if calendar is None:
        return s
    cal = pd.DatetimeIndex(calendar)
    return s.reindex(s.index.union(cal)).ffill(limit=3).reindex(cal)


def fed_expected_move(kalshi: pd.DataFrame, meeting_dates: dict[str, str], calendar=None) -> pd.DataFrame:
    """Expected policy move (bp) at the next FOMC meeting, and its daily change.

    The change is always computed on the same meeting contract, so the roll from one
    meeting to the next never creates an artificial jump; on decision day the change
    is the policy surprise itself.
    """
    k = kalshi.rename(columns={"price": "mid"}).dropna(subset=["mid"]).copy()
    k["date"] = pd.to_datetime(k["date"])  # US Eastern trading day (see sources.kalshi.candles)
    k["bp"] = k["outcome"].map(OUTCOME_BP)
    piv = k.pivot_table(index=["date", "meeting"], columns="outcome", values="mid")
    ok = piv.notna().sum(axis=1) >= 3
    piv = piv[ok]
    probs = piv.div(piv.sum(axis=1), axis=0)
    bp = pd.Series(OUTCOME_BP)[probs.columns]
    e = (probs * bp).sum(axis=1).rename("E").reset_index()
    e["p_hike"] = probs.reindex(columns=["H25", "H26"]).sum(axis=1).values
    e["p_cut"] = probs.reindex(columns=["C25", "C26"]).sum(axis=1).values
    if calendar is not None:  # move each meeting's series onto the trading calendar before differencing
        parts = []
        for m, g in e.groupby("meeting"):
            g = g.set_index("date")[["E", "p_hike", "p_cut"]]
            g = g.apply(lambda c: _on_calendar(c, calendar[(calendar >= g.index.min()) & (calendar <= g.index.max())]))
            parts.append(g.dropna(how="all").assign(meeting=m).rename_axis("date").reset_index())
        e = pd.concat(parts, ignore_index=True)
    e = e.sort_values(["meeting", "date"])
    e["dE"] = e.groupby("meeting")["E"].diff()
    e["dp_hike"] = e.groupby("meeting")["p_hike"].diff()
    md = {m: pd.Timestamp(d) for m, d in meeting_dates.items()}
    e["mdate"] = e["meeting"].map(md)
    e = e[e["date"] <= e["mdate"]]
    nxt = e.loc[e.groupby("date")["mdate"].idxmin()].set_index("date").sort_index()
    return nxt[["meeting", "E", "p_hike", "p_cut", "dE", "dp_hike"]]


def event_probs(poly: pd.DataFrame, col: str = "key") -> pd.DataFrame:
    """Wide table of daily probabilities (US Eastern daily close), one column per event key."""
    p = poly[poly[col].fillna("") != ""].copy()
    p["date"] = pd.to_datetime(p["date"])
    return p.pivot_table(index="date", columns=col, values="prob").sort_index()


def event_changes(wide: pd.DataFrame, max_jump: float = 0.5, calendar=None) -> pd.DataFrame:
    """Change between trading days in percentage points; drops resolved and degenerate days.

    With a calendar (e.g. NYSE dates) the change on Monday covers Friday to Monday, like returns.
    """
    if calendar is not None:
        wide = wide.apply(lambda c: _on_calendar(c.dropna(), calendar))
    d = wide.diff()
    pinned = (wide.shift(1).le(0.005) & wide.le(0.005)) | (wide.shift(1).ge(0.995) & wide.ge(0.995))
    d = d.mask(pinned).mask(d.abs() > max_jump)
    return d * 100


def asset_returns(prices: pd.DataFrame) -> pd.DataFrame:
    """Daily returns in % (changes in points or bp for VIX and yields), each series on its own calendar."""
    val = "close" if "close" in prices else "adj_close"
    p = prices.assign(date=pd.to_datetime(prices["date"], format="mixed").dt.normalize())
    wide = p.pivot_table(index="date", columns="ticker", values=val).sort_index()
    out = {}
    for t in wide:
        s = wide[t].dropna()
        out[t] = s.diff() * LEVEL_SERIES[t] if t in LEVEL_SERIES else s.pct_change() * 100
    return pd.DataFrame(out)


# --------------------------------------------------------------------- estimation
def ols_hac(y: np.ndarray, X: np.ndarray, lags: int = 3):
    """OLS with an intercept already in X; Newey West (Bartlett) covariance."""
    n, k = X.shape
    XtX_inv = np.linalg.pinv(X.T @ X)
    b = XtX_inv @ X.T @ y
    u = y - X @ b
    Xu = X * u[:, None]
    S = Xu.T @ Xu
    for L in range(1, lags + 1):
        w = 1 - L / (lags + 1)
        G = Xu[L:].T @ Xu[:-L]
        S += w * (G + G.T)
    V = XtX_inv @ S @ XtX_inv * n / max(n - k, 1)
    se = np.sqrt(np.diag(V))
    r2 = 1 - (u @ u) / (((y - y.mean()) ** 2).sum())
    return b, se, r2, n


def event_betas(rets: pd.DataFrame, shocks: pd.DataFrame, scale: dict | None = None,
                control: pd.Series | None = None, min_obs: int = 60, lags: int = 3) -> pd.DataFrame:
    """One regression per (asset, event): r = a + g * shock (+ c * control) + e.

    scale rescales the shock unit, e.g. {"us_invades_iran": 10} -> beta per +10pp.
    Returns a long table with beta, t stat, R2 and number of observations.
    """
    scale = scale or {}
    rows = []
    for ev in shocks.columns:
        s = shocks[ev] / scale.get(ev, 1.0)
        for a in rets.columns:
            cols = [rets[a], s] + ([control] if control is not None and a != control.name else [])
            df = pd.concat(cols, axis=1, join="inner").dropna()
            if len(df) < min_obs:
                continue
            y = df.iloc[:, 0].values
            X = np.column_stack([np.ones(len(df))] + [df.iloc[:, j].values for j in range(1, df.shape[1])])
            b, se, r2, n = ols_hac(y, X, lags)
            rows.append({"asset": a, "event": ev, "beta": b[1], "t": b[1] / se[1], "r2": r2, "n": n})
    return pd.DataFrame(rows)


def portfolio_exposure(betas: pd.DataFrame, weights: dict[str, float]) -> pd.Series:
    """Portfolio event beta = sum of weight times asset event beta."""
    piv = betas.pivot(index="asset", columns="event", values="beta")
    w = pd.Series(weights)
    return (piv.reindex(w.index).mul(w, axis=0)).sum(min_count=1)


def scenario(exposure: pd.Series, shocks: dict[str, float], units: dict[str, float]) -> float:
    """P&L in % for shocks expressed in the same units as the event betas."""
    return float(sum(exposure[e] * shocks[e] / units.get(e, 1.0) for e in shocks))


def hedge_ratio(port_beta: float, hedge_beta: float) -> float:
    """Weight in the hedge asset that sets the portfolio's event beta to zero."""
    return -port_beta / hedge_beta
