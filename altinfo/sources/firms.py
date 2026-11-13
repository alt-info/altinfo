"""NASA FIRMS active fires (free, no key): https://firms.modaps.eosdis.nasa.gov/active_fire/

The public text files cover the whole world for the last 24 hours, 48 hours or 7 days.
MODIS has 1 km pixels and a smaller file than VIIRS; it is enough to flag a fire near a mine or a field.
"""
import io
import urllib.request

import pandas as pd

from .http import HEADERS, _report

URL = "https://firms.modaps.eosdis.nasa.gov/data/active_fire/modis-c6.1/csv/MODIS_C6_1_Global_{period}.csv"


def fires(period="7d", min_confidence=50):
    """Active fires: time, lat, lon, frp (fire radiative power, MW), confidence. period: 24h, 48h or 7d."""
    url = URL.format(period=period)
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=120) as r:
            df = pd.read_csv(io.BytesIO(r.read()))
    except Exception as e:
        _report(url, f"{type(e).__name__}: {e}")
        return pd.DataFrame(columns=["time", "lat", "lon", "frp", "confidence"])
    t = pd.to_datetime(df["acq_date"] + " " + df["acq_time"].astype(str).str.zfill(4), format="%Y-%m-%d %H%M", utc=True)
    out = pd.DataFrame({"time": t, "lat": df["latitude"], "lon": df["longitude"], "frp": df["frp"],
                        "confidence": pd.to_numeric(df["confidence"], errors="coerce")})
    return out[out["confidence"] >= min_confidence].reset_index(drop=True)
