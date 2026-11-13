"""Track record: score every call against the market after the event."""
import numpy as np
import pandas as pd


def brier(p, outcome):
    """Mean squared error of a probability forecast; 0 is perfect, 0.25 is a coin flip."""
    p, o = np.asarray(p, float), np.asarray(outcome, float)
    return float(np.mean((p - o) ** 2))


def log_score(p, outcome, eps=1e-6):
    p, o = np.clip(np.asarray(p, float), eps, 1 - eps), np.asarray(outcome, float)
    return float(-np.mean(o * np.log(p) + (1 - o) * np.log(1 - p)))


def track_record(calls: pd.DataFrame):
    """calls: columns event, ours, market, outcome (1, 0 or empty if unresolved).

    Returns per call scores and an overall line with the Brier skill score against the market
    (positive = we beat the market).
    """
    c = calls.copy()
    done = c["outcome"].notna()
    c.loc[done, "brier_ours"] = (c.loc[done, "ours"] - c.loc[done, "outcome"]) ** 2
    c.loc[done, "brier_market"] = (c.loc[done, "market"] - c.loc[done, "outcome"]) ** 2
    if done.any():
        bo, bm = c.loc[done, "brier_ours"].mean(), c.loc[done, "brier_market"].mean()
        summary = {"resolved": int(done.sum()), "brier_ours": bo, "brier_market": bm,
                   "skill_vs_market": 1 - bo / bm if bm > 0 else np.nan}
    else:
        summary = {"resolved": 0, "brier_ours": np.nan, "brier_market": np.nan, "skill_vs_market": np.nan}
    return c, summary
