"""Earnings reactions: how the stock moved the day after each report."""
import pandas as pd

# NVIDIA reports after the US close; dates from NVIDIA press releases
NVDA_REPORTS = {
    "Q3 FY25": "2024-11-20", "Q4 FY25": "2025-02-26", "Q1 FY26": "2025-05-28", "Q2 FY26": "2025-08-27",
    "Q3 FY26": "2025-11-19", "Q4 FY26": "2026-02-25", "Q1 FY27": "2026-05-20", "Q2 FY27": "2026-08-26",
}


def next_day_moves(px: pd.Series, reports: dict, after_close=True):
    """Close to close return from the report day to the next trading day (after close reports)."""
    px = px.dropna().sort_index()
    rows = []
    for q, d in reports.items():
        d = pd.Timestamp(d)
        before = px.loc[:d] if after_close else px.loc[:d - pd.Timedelta(days=1)]
        after = px.loc[d + pd.Timedelta(days=1):] if after_close else px.loc[d:]
        if before.empty or after.empty:
            continue
        rows.append({"quarter": q, "report": d.date(), "reaction_day": after.index[0].date(),
                     "close_before": before.iloc[-1], "close_after": after.iloc[0],
                     "move": after.iloc[0] / before.iloc[-1] - 1})
    return pd.DataFrame(rows)


def reaction_summary(moves: pd.DataFrame):
    return {"reports": len(moves), "negative": int((moves.move < 0).sum()),
            "avg_abs_move": float(moves.move.abs().mean()), "worst": float(moves.move.min()),
            "best": float(moves.move.max())}


def drawdown_from_high(px: pd.Series):
    """Distance of the last price from the running maximum and the date of that maximum."""
    px = px.dropna()
    hi_date = px.idxmax()
    return {"last": float(px.iloc[-1]), "high": float(px.max()), "high_date": hi_date.date(),
            "distance": float(px.iloc[-1] / px.max() - 1)}
