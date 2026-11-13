"""Physical indices from satellite observations.

The observations themselves (stage of each campus, shadow lengths in each tank) come from
imagery analysts or computer vision; this module turns them into the indices shown in the
previews. Prototype inputs live in data/prototype and are illustrative.
"""
import pandas as pd

# Weight of each construction stage in the Data Center Build-out Index (NVIDIA preview, p. 2)
STAGE_WEIGHTS = {"site_prep": 0.15, "shell": 0.40, "roof_mech": 0.60, "power_cooling": 0.85, "energized": 1.00}
FIT_OUT = ("power_cooling", "energized")  # chips are being installed or running


def buildout_index(campuses: pd.DataFrame, stage_col="stage", gw_col="gw"):
    """Capacity weighted completion of AI data centre campuses (0 to 1)."""
    w = campuses[stage_col].map(STAGE_WEIGHTS)
    return float((w * campuses[gw_col]).sum() / campuses[gw_col].sum())


def gw_in_fit_out(campuses: pd.DataFrame, stage_col="stage", gw_col="gw"):
    return float(campuses.loc[campuses[stage_col].isin(FIT_OUT), gw_col].sum())


def buildout_history(panel: pd.DataFrame):
    """panel: one row per campus and quarter (campus, gw, quarter, stage) -> index and GW by quarter."""
    out = panel.groupby("quarter", sort=False).apply(
        lambda d: pd.Series({"index": buildout_index(d), "gw_fit_out": gw_in_fit_out(d), "campuses": len(d)}),
        include_groups=False)
    return out


def tank_fill(inner_shadow, outer_shadow):
    """Fill of a floating roof tank from two shadows measured on the same image.

    The outer shadow (cast by the wall on the ground) gives the wall height, the inner shadow
    (cast by the rim on the floating roof) gives how far the roof sits below the rim. With the
    same sun elevation both scale with tan(elevation), so fill = 1 - inner / outer.
    """
    return max(0.0, min(1.0, 1 - inner_shadow / outer_shadow))


def tank_table(tanks: pd.DataFrame):
    """tanks: hub, date, inner, outer, capacity -> capacity weighted fill by hub and date."""
    t = tanks.copy()
    t["fill"] = [tank_fill(i, o) for i, o in zip(t["inner"], t["outer"])]
    t["oil"] = t["fill"] * t["capacity"]
    g = t.groupby(["hub", "date"])[["oil", "capacity"]].sum()
    return (g["oil"] / g["capacity"]).unstack("date")
