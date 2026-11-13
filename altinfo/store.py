"""Storage: a cache for downloads and the history of every analysis, in one SQLite file (standard library).

cache      get / put a JSON payload by (source, key) with a time to live; stale entries are kept as a fallback
           for when a source is down
analyses   every analysis the engine produced, so the platform can show how probabilities, gaps and prices changed
watchlist  the tickers the user saved in the track record (one shared list until user accounts exist)
series     time series the engine wants to keep (market probability, our probability, price) by asset

Swap this module for Postgres or Redis later without touching the engine: only these functions are used.
"""
import json
import sqlite3
import threading
import time

from . import config

_lock = threading.Lock()
_conn = None


def _db():
    global _conn
    if _conn is None:
        config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(str(config.DB_PATH), check_same_thread=False)
        _conn.executescript("""
        CREATE TABLE IF NOT EXISTS cache (source TEXT, key TEXT, fetched_at REAL, payload TEXT, PRIMARY KEY (source, key));
        CREATE TABLE IF NOT EXISTS analyses (id INTEGER PRIMARY KEY AUTOINCREMENT, asset TEXT, created_at REAL, payload TEXT);
        CREATE INDEX IF NOT EXISTS ix_an ON analyses (asset, created_at);
        CREATE TABLE IF NOT EXISTS series (asset TEXT, name TEXT, day TEXT, value REAL, PRIMARY KEY (asset, name, day));
        CREATE TABLE IF NOT EXISTS watchlist (asset TEXT PRIMARY KEY, name TEXT, query TEXT, added_at REAL);
        CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
        """)
        # the two calls of the event reports are in the track record from the start (once: removing them is respected)
        if not _conn.execute("SELECT 1 FROM meta WHERE k='seeded'").fetchone():
            _conn.executemany("INSERT OR IGNORE INTO watchlist VALUES (?,?,?,?)",
                              [("NVDA", "NVIDIA", "NVDA", time.time()), ("BRENT", "Brent crude", "Brent", time.time() + 0.001)])
            _conn.execute("INSERT INTO meta VALUES ('seeded', '1')")
            _conn.commit()
    return _conn


# ------------------------------------------------------------------ cache
def cache_get(source, key, ttl=None):
    """Return (payload, age_seconds) or (None, None). With ttl, entries older than ttl are not returned."""
    with _lock:
        r = _db().execute("SELECT fetched_at, payload FROM cache WHERE source=? AND key=?", (source, key)).fetchone()
    if not r:
        return None, None
    age = time.time() - r[0]
    if ttl is not None and age > ttl:
        return None, age
    return json.loads(r[1]), age


def cache_put(source, key, payload):
    with _lock:
        _db().execute("INSERT OR REPLACE INTO cache VALUES (?,?,?,?)", (source, key, time.time(), json.dumps(payload, default=str)))
        _db().commit()


def cache_clear_key(source, key):
    with _lock:
        _db().execute("DELETE FROM cache WHERE source=? AND key=?", (source, key))
        _db().commit()


def cache_clear(source=None):
    with _lock:
        _db().execute("DELETE FROM cache" + (" WHERE source=?" if source else ""), (source,) if source else ())
        _db().commit()


# ------------------------------------------------------------------ history
def save_analysis(asset, payload):
    with _lock:
        _db().execute("INSERT INTO analyses (asset, created_at, payload) VALUES (?,?,?)",
                      (asset, time.time(), json.dumps(payload, default=str)))
        _db().commit()


def past_analyses(asset, limit=200):
    """Headline numbers of the past analyses of an asset, oldest first."""
    with _lock:
        rows = _db().execute("SELECT created_at, payload FROM analyses WHERE asset=? ORDER BY created_at DESC LIMIT ?",
                             (asset, limit)).fetchall()
    out = []
    for ts, p in reversed(rows):
        d = json.loads(p)
        h = d.get("headline") or {}
        out.append({"at": ts, "price": (d.get("price") or {}).get("last"), "ours": h.get("ours"), "market": h.get("market"),
                    "gap_pts": h.get("gap_pts"), "label": h.get("label"), "question": h.get("question"), "basis": h.get("basis"),
                    "confidence": (d.get("confidence") or {}).get("score"), "level": (d.get("confidence") or {}).get("level"),
                    "coverage": (d.get("asset") or {}).get("coverage"), "report": (d.get("asset") or {}).get("report"),
                    "title": (d.get("conclusion") or {}).get("title")})
    return out


def latest_analysis(asset):
    """The full payload of the most recent analysis of an asset, or None."""
    with _lock:
        r = _db().execute("SELECT created_at, payload FROM analyses WHERE asset=? ORDER BY created_at DESC LIMIT 1",
                          (asset,)).fetchone()
    return (r[0], json.loads(r[1])) if r else (None, None)


# ------------------------------------------------------------------ watchlist (track record and dashboard)
def watch_add(asset, name, query):
    with _lock:
        _db().execute("INSERT OR IGNORE INTO watchlist VALUES (?,?,?,?)", (asset, name, query, time.time()))
        _db().commit()


def watch_remove(asset):
    with _lock:
        _db().execute("DELETE FROM watchlist WHERE asset=?", (asset,))
        _db().commit()


def watch_list():
    with _lock:
        rows = _db().execute("SELECT asset, name, query, added_at FROM watchlist ORDER BY added_at").fetchall()
    return [{"key": a, "name": n, "query": q, "added_at": t} for a, n, q, t in rows]


def put_series(asset, name, points):
    """points: iterable of (day 'YYYY-MM-DD', value). Existing days are overwritten."""
    with _lock:
        _db().executemany("INSERT OR REPLACE INTO series VALUES (?,?,?,?)",
                          [(asset, name, str(d)[:10], float(v)) for d, v in points if v is not None and v == v])
        _db().commit()


def get_series(asset, name):
    with _lock:
        rows = _db().execute("SELECT day, value FROM series WHERE asset=? AND name=? ORDER BY day", (asset, name)).fetchall()
    return [{"t": d, "v": v} for d, v in rows]
