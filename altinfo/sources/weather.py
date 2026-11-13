"""Daily weather for any point on Earth from Open-Meteo (free, no key, ERA5 reanalysis): https://open-meteo.com

Used for the agriculture signals: rain and temperature in the key growing regions against normal.
"""
import pandas as pd

from .http import get_json

URL = "https://archive-api.open-meteo.com/v1/archive"


def daily(lat, lon, start, end):
    """Daily precipitation (mm) and mean temperature (C)."""
    js = get_json(URL, {"latitude": lat, "longitude": lon, "start_date": start, "end_date": end,
                        "daily": "precipitation_sum,temperature_2m_mean", "timezone": "UTC"}, tries=2)
    if not js or "daily" not in js:
        return pd.DataFrame(columns=["date", "precip", "tmean"])
    d = js["daily"]
    return pd.DataFrame({"date": pd.to_datetime(d["time"]), "precip": d["precipitation_sum"], "tmean": d["temperature_2m_mean"]})


def anomaly(df, days=30, years=10):
    """Last `days` days against the same calendar window in the previous `years` years.

    Returns rain over the window (mm), its normal, rain as % of normal and the temperature anomaly (C)."""
    df = df.dropna().sort_values("date")
    if df.empty:
        return None
    end = df["date"].max()
    start = end - pd.Timedelta(days=days - 1)
    now = df[df.date >= start]
    past = []
    for y in range(1, years + 1):
        s, e = start - pd.DateOffset(years=y), end - pd.DateOffset(years=y)
        w = df[(df.date >= s) & (df.date <= e)]
        if len(w) >= days * 0.9:
            past.append((w["precip"].sum(), w["tmean"].mean()))
    if not past:
        return None
    rain_n = sum(p for p, _ in past) / len(past)
    t_n = sum(t for _, t in past) / len(past)
    rain = now["precip"].sum()
    return {"window_end": end, "rain_mm": rain, "rain_normal_mm": rain_n,
            "rain_pct_normal": rain / rain_n if rain_n > 0 else None, "temp_anomaly_c": now["tmean"].mean() - t_n}
