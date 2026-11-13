"""Personalized monitors: what to watch, which signal, when to trigger, what happens.

A monitor is a list of sites (or assets), a set of signal functions and a trigger rule. `run` evaluates
the rule and returns alerts with a short text, the share of output at risk and how much prices have
already moved. Free disaster feeds (USGS earthquakes) make monitors cheap to run; paid imagery is only
needed to confirm the impact.
"""
from dataclasses import dataclass, field
from math import asin, cos, radians, sin, sqrt
from typing import Callable

import pandas as pd


def km_between(lat1, lon1, lat2, lon2):
    """Great circle distance (haversine), km."""
    p1, p2 = radians(lat1), radians(lat2)
    a = sin((p2 - p1) / 2) ** 2 + cos(p1) * cos(p2) * sin(radians(lon2 - lon1) / 2) ** 2
    return 2 * 6371.0 * asin(sqrt(a))


# ---------------------------------------------------------------- signals
def disasters_near(sites, events, radius_km=30.0, min_mag=4.5):
    """Events (lat, lon, mag, time, place) within radius_km of each site."""
    rows = []
    for s in sites:
        for e in events.itertuples():
            if e.mag is not None and e.mag >= min_mag:
                d = km_between(s["lat"], s["lon"], e.lat, e.lon)
                if d <= radius_km:
                    rows.append({"site": s["site"], "time": e.time, "mag": e.mag, "km": round(d, 1), "place": e.place})
    return pd.DataFrame(rows, columns=["site", "time", "mag", "km", "place"])


def fires_near(sites, fires, radius_km=30.0, min_frp=0.0):
    """Active fires (NASA FIRMS: time, lat, lon, frp) within radius_km of each site."""
    rows = []
    for s in sites:
        for e in fires.itertuples():
            if e.frp >= min_frp:
                d = km_between(s["lat"], s["lon"], e.lat, e.lon)
                if d <= radius_km:
                    rows.append({"site": s["site"], "time": e.time, "frp": e.frp, "km": round(d, 1)})
    return pd.DataFrame(rows, columns=["site", "time", "frp", "km"])


def site_alerts(sites, quakes=None, fires=None, quake_km=100.0, fire_km=30.0):
    """Live alerts on a list of places: earthquakes M4.5+ within quake_km, fires within fire_km. One row per site."""
    rows, seen = [], set()
    sites = [s for s in sites if not (s["site"] in seen or seen.add(s["site"]))]  # a place listed twice is checked once
    q = disasters_near(sites, quakes, quake_km) if quakes is not None and len(quakes) else pd.DataFrame(columns=["site"])
    f = fires_near(sites, fires, fire_km) if fires is not None and len(fires) else pd.DataFrame(columns=["site"])
    for s in sites:
        qs, fs = q[q.site == s["site"]], f[f.site == s["site"]]
        if len(qs):
            r = qs.sort_values("mag").iloc[-1]
            rows.append({"site": s["site"], "alert": f"Earthquake M{r.mag:.1f}, {r.km:.0f} km away", "time": r.time})
        if len(fs):
            rows.append({"site": s["site"], "alert": f"{len(fs)} active fire{'s' if len(fs) > 1 else ''} within {fire_km:.0f} km",
                         "time": fs.time.max()})
    return pd.DataFrame(rows, columns=["site", "alert", "time"])


def activity_drop(activity: pd.Series, window=28):
    """Latest activity versus its trailing average (e.g. trucks and staff parking counted from imagery)."""
    base = activity.rolling(window, min_periods=window // 2).mean().shift(1)
    return activity / base - 1


def market_jumps(history: pd.DataFrame, threshold_pts=10.0):
    """Days when a prediction market probability moved by threshold_pts or more. history: date, key, prob."""
    h = history.sort_values("date").copy()
    h["move_pts"] = h.groupby("key")["prob"].diff() * 100
    return h[h["move_pts"].abs() >= threshold_pts][["date", "key", "prob", "move_pts"]]


# ---------------------------------------------------------------- monitor
@dataclass
class Monitor:
    name: str
    sites: list
    rule: Callable  # (context) -> list of alert dicts
    channels: list = field(default_factory=lambda: ["email", "app"])

    def run(self, **context):
        alerts = self.rule(self, **context)
        return pd.DataFrame(alerts)


COPPER_PRODUCERS = ["FCX", "SCCO", "TECK", "BHP", "GLEN", "IVN"]
COPPER_USERS = ["PRY.MI"]  # cable makers: copper is their main input cost


def gainers_losers(owners, producers=COPPER_PRODUCERS, users=COPPER_USERS):
    """Who is likely to gain or lose when a mine stops: its owners lose volume and users pay more;
    producers elsewhere sell into a tighter market at a higher price."""
    lose = list(owners) + [u for u in users if u not in owners]
    gain = [p for p in producers if p not in owners] + ["copper futures (long)"]
    return ", ".join(gain), ", ".join(lose)


def copper_rule(m, quakes=None, activity=None, prices=None, asof=None, radius_km=30.0, min_output=0.10,
                drop=-0.20, horizon=None):
    """Copper supply disruption: disaster within radius of a mine that is > min_output of a company's output,
    AND activity at the site more than 20% below its 4 week average. Either leg alone is reported as a watch."""
    out = []
    near = disasters_near(m.sites, quakes, radius_km) if quakes is not None and len(quakes) else pd.DataFrame()
    for s in m.sites:
        big = {c: w for c, w in s["owners"].items() if w >= min_output}
        if not big:
            continue
        act = activity.get(s["site"]) if activity else None
        chg = activity_drop(act).loc[:asof].iloc[-1] if act is not None else None
        hit_q = len(near) and (near["site"] == s["site"]).any()
        hit_a = chg is not None and chg <= drop
        if not (hit_q or hit_a):
            continue
        level = "ALERT" if (hit_q and hit_a) or (hit_a and quakes is None) else "WATCH"
        moves = {}
        if prices is not None and asof is not None:
            for t in list(big) + ["HG=F"]:
                if t in prices:
                    p = prices[t].dropna()
                    start = p.loc[:asof].index[-1] if len(p.loc[:asof]) else None
                    if start is not None:
                        end = p.loc[:horizon].iloc[-1] if horizon is not None else p.iloc[-1]
                        moves[t] = end / p.loc[start] - 1
        out.append({"level": level, "site": s["site"], "country": s["country"],
                    "trigger": " + ".join(x for x, y in [("disaster within %d km" % radius_km, hit_q),
                                                         (f"activity {chg:+.0%} vs 4w avg" if chg is not None else "", hit_a)] if y),
                    "output_at_risk": ", ".join(f"{c} {w:.0%}" for c, w in big.items()),
                    "moves_since": ", ".join(f"{t} {v:+.1%}" for t, v in moves.items()),
                    "likely_gain": gainers_losers(big)[0], "likely_lose": gainers_losers(big)[1],
                    "channels": "/".join(m.channels)})
    return out
