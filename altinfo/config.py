"""Settings and secrets. Read ONLY by the backend: nothing here is ever sent to the browser.

Secrets come from environment variables or from a `.env` file in the project folder (never committed to Git,
see .gitignore). Example .env:

    EIA_API_KEY=your_key_here

Sources that need a key degrade gracefully when the key is missing (EIA falls back to the figures in the snapshot).
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_env(path=ROOT / ".env"):
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env()

# ---- secrets (backend only)
EIA_API_KEY = os.environ.get("EIA_API_KEY", "")           # free: https://www.eia.gov/opendata/register.php
# Place holders for paid sources the prototype does not use yet:
X_BEARER_TOKEN = os.environ.get("X_BEARER_TOKEN", "")     # attention on X
PLANET_API_KEY = os.environ.get("PLANET_API_KEY", "")     # satellite imagery
KPLER_TOKEN = os.environ.get("KPLER_TOKEN", "")           # ship tracking

# ---- storage
DB_PATH = Path(os.environ.get("ALTINFO_DB", ROOT / "data" / "altinfo.db"))
RAW = ROOT / "data" / "raw"            # files written by scripts/fetch_data.py, used as offline fallback
PROTO = ROOT / "data" / "prototype"
SNAPSHOT = ROOT / "data" / "snapshot_2026-11-09.json"

# ---- cache: seconds a download stays fresh, by source
TTL = {"prices": 15 * 60, "kalshi": 5 * 60, "polymarket": 5 * 60, "usgs": 30 * 60, "firms": 3 * 3600,
       "weather": 12 * 3600, "eia": 6 * 3600, "fundamentals": 12 * 3600, "resolver": 24 * 3600, "curve": 30 * 60}

# ---- server
HOST = os.environ.get("ALTINFO_HOST", "127.0.0.1")       # local only by default
PORT = int(os.environ.get("ALTINFO_PORT", "8000"))
PRICED_IN_THRESHOLD = 0.03                                 # |gap| below 3 points = priced in


def public_config():
    """The only settings the frontend may see: no secrets, just which optional sources are switched on."""
    return {"eia_live": bool(EIA_API_KEY), "threshold_pts": PRICED_IN_THRESHOLD * 100}
