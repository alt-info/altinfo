"""US Energy Information Administration open data (API v2, free key): https://www.eia.gov/opendata/

weekly_petroleum   commercial crude, SPR and distillate stocks, refinery utilisation (Weekly Petroleum Status Report)
steo_brent         the EIA's own Brent forecast (Short-Term Energy Outlook)
The key is read by the backend from config.EIA_API_KEY and is never sent to the browser.
"""
import pandas as pd

from .http import get_json

BASE = "https://api.eia.gov/v2"
WEEKLY = {"WCESTUS1": ("petroleum/stoc/wstk", "commercial_crude_kb"), "WCSSTUS1": ("petroleum/stoc/wstk", "spr_kb"),
          "WDISTUS1": ("petroleum/stoc/wstk", "distillate_kb"), "WPULEUS3": ("petroleum/pnp/wiup", "refinery_utilisation_pct")}


def _series(route, facet, sid, key, frequency, length):
    params = [("api_key", key), ("frequency", frequency), ("data[0]", "value"), (f"facets[{facet}][]", sid),
              ("sort[0][column]", "period"), ("sort[0][direction]", "desc"), ("length", length)]
    js = get_json(f"{BASE}/{route}/data/", params, tries=2)
    rows = ((js or {}).get("response") or {}).get("data") or []
    s = pd.Series({pd.Timestamp(r["period"]): float(r["value"]) for r in rows if r.get("value") is not None}, dtype=float)
    return s.sort_index()


def weekly_petroleum(key, years=6):
    """DataFrame indexed by week ending date with one column per series, about `years` years back."""
    cols = {name: _series(route, "series", sid, key, "weekly", years * 53) for sid, (route, name) in WEEKLY.items()}
    df = pd.DataFrame(cols).dropna(how="all")
    return df


def vs_five_year(s: pd.Series):
    """Latest value against the average of the same week of the year in the previous five years."""
    s = s.dropna()
    if len(s) < 60:
        return None
    last, wk = s.index[-1], s.index[-1].isocalendar()[1]
    past = [s[(s.index.year == last.year - k) & (s.index.isocalendar().week.values == wk)] for k in range(1, 6)]
    past = [p.iloc[0] for p in past if len(p)]
    return s.iloc[-1] / (sum(past) / len(past)) - 1 if len(past) >= 3 else None


def summary(df: pd.DataFrame):
    """The figures the Brent and WTI reports quote, computed from the weekly series."""
    if df is None or df.empty:
        return None
    out = {"week_ending": df.index[-1].strftime("%Y-%m-%d")}
    if "commercial_crude_kb" in df:
        c = df["commercial_crude_kb"].dropna()
        out["commercial_crude_mb"] = round(c.iloc[-1] / 1000, 1)
        out["crude_change_mb"] = round((c.iloc[-1] - c.iloc[-2]) / 1000, 1) if len(c) > 1 else None
        out["crude_vs_5y"] = vs_five_year(c)
    if "distillate_kb" in df:
        out["distillates_vs_5y"] = vs_five_year(df["distillate_kb"])
    if "spr_kb" in df:
        s = df["spr_kb"].dropna()
        out["spr_yoy"] = s.iloc[-1] / s.iloc[-53] - 1 if len(s) > 53 else None
    if "refinery_utilisation_pct" in df:
        out["refinery_utilisation"] = df["refinery_utilisation_pct"].dropna().iloc[-1] / 100
    return out


def steo_brent(key):
    """Monthly Brent spot price, history and forecast, from the latest Short-Term Energy Outlook ($/bbl)."""
    return _series("steo", "seriesId", "BREPUUS", key, "monthly", 60)
