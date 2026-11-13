"""US Geological Survey earthquake feed (free, no key): https://earthquake.usgs.gov/earthquakes/feed/"""
import pandas as pd

from .http import get_json

FEED = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/{level}_{period}.geojson"


def earthquakes(level="4.5", period="month"):
    """Recent earthquakes: time, magnitude, place, lat, lon. level: significant, 4.5, 2.5; period: day, week, month."""
    js = get_json(FEED.format(level=level, period=period)) or {}
    rows = []
    for f in js.get("features", []):
        lon, lat = f["geometry"]["coordinates"][:2]
        p = f["properties"]
        rows.append({"time": pd.to_datetime(p["time"], unit="ms", utc=True), "mag": p.get("mag"),
                     "place": p.get("place"), "lat": lat, "lon": lon, "url": p.get("url")})
    return pd.DataFrame(rows, columns=["time", "mag", "place", "lat", "lon", "url"])
