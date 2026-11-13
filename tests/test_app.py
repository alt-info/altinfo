"""Tests of the on demand pipeline, offline (saved files only): python tests/test_app.py"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["ALTINFO_DB"] = os.path.join(tempfile.mkdtemp(), "test.db")
os.environ["ALTINFO_OFFLINE"] = "1"
from altinfo import engine, normalize, resolver, store  # noqa: E402
from altinfo.errors import InvalidQuery, UnknownAsset  # noqa: E402
from altinfo.fetch import Fetcher  # noqa: E402

HAVE_RAW = os.path.exists(os.path.join(ROOT, "data", "raw", "prices.csv"))


def test_resolver_rejects_bad_input():
    f = Fetcher(offline=True)
    for bad in ["", "<script>", "a" * 60, "DROP TABLE;"]:
        try:
            resolver.resolve(bad, f)
            assert False, bad
        except InvalidQuery:
            pass
    try:
        resolver.resolve("zzzzqq", f)
        assert False
    except UnknownAsset:
        pass


def test_relevance_filter():
    a = resolver.resolve("gold", Fetcher(offline=True))
    assert not resolver.relevant("Will Emily Blunt be nominated at the 84th Golden Globe Awards?", a)
    assert resolver.relevant("Will Gold (GC) hit (HIGH) $5,000 by end of December?", a)


def test_model_probability():
    assert abs(engine.model_prob("price_above", 100, 100, 0.02, 25) - 0.48) < 0.02
    assert engine.model_prob("price_above", 100, 150, 0.02, 25) < 0.01
    assert engine.model_prob("touch_high", 100, 90, 0.02, 25) == 1.0
    assert engine.model_prob("touch_low", 100, 110, 0.02, 25) == 1.0


def test_contract_kinds():
    assert normalize._kind_poly("Will NVIDIA (NVDA) close above $200 end of November?") == "price_above"
    assert normalize._kind_poly("Will Nvidia (NVDA) beat quarterly earnings?") == "earnings_beat"
    assert normalize._kind_kalshi("Will the brent crude oil close price be above 95.99 USD/Bbl?", 95.99) == "price_above"
    assert normalize._kind_kalshi("What will NVIDIA Corporation say during their next earnings call?", float("nan")) == "mention"


def test_live_api_text_numbers():
    """The live Kalshi API sends prices as text ("0.4500"): the normaliser must accept both."""
    import pandas as pd
    df = pd.DataFrame([{"ticker": "X-T96", "title": "Will the brent crude oil close price be above 95.99 USD/Bbl?",
                        "yes_sub_title": "Above $95.99", "yes_bid_dollars": "0.2500", "yes_ask_dollars": "0.2700",
                        "last_price_dollars": "0.2600", "volume_fp": "1200.00", "floor_strike": "95.99",
                        "close_time": "2026-11-30T22:00:00Z", "series": "KXBRENTMON"}])
    c = normalize.kalshi_contracts(df)[0]
    assert abs(c["prob"] - 0.26) < 1e-9 and c["level"] == 95.99 and c["kind"] == "price_above"
    p = normalize.poly_contracts(pd.DataFrame([{"question": "Will Nvidia (NVDA) beat quarterly earnings?", "price": "0.94",
                                                 "volume": "900", "end": "2026-11-17", "market_slug": "s"}]))[0]
    assert p["prob"] == 0.94 and p["kind"] == "earnings_beat"


def test_two_venues_are_blended_by_volume():
    cs = [{"venue": "Kalshi", "kind": "price_above", "level": 95.99, "closes": "2026-11-30", "prob": 0.30, "volume": 3000},
          {"venue": "Kalshi", "kind": "price_above", "level": 100.0, "closes": "2026-11-30", "prob": 0.10, "volume": 1000},
          {"venue": "Polymarket", "kind": "price_above", "level": 96.0, "closes": "2026-11-30", "prob": 0.40, "volume": 1000}]
    g = {"question": "q", "ours": 0.62, "market": 0.30, "kind": "price_above", "level": 96.0, "closes": "2026-11-30"}
    engine._blend(g, cs)
    k = [x for x in g["quotes"] if x["venue"] == "Kalshi"][0]
    assert len(g["quotes"]) == 2 and 0.29 < k["prob"] < 0.31          # Kalshi interpolated at 96 from its ladder
    assert abs(g["market"] - (k["prob"] * k["volume"] + 0.40 * 1000) / (k["volume"] + 1000)) < 1e-3 and g["venue_spread_pts"] >= 9


def test_gdelt_timeline_parsing():
    from altinfo.sources import gdelt
    js = {"timeline": [{"series": "Volume Intensity", "data": [{"date": "20261109T000000Z", "value": 0.1},
                                                               {"date": "20261110T000000Z", "value": 0.3}]}]}
    s = gdelt._timeline(js)
    assert list(s.values) == [0.1, 0.3] and str(s.index[-1].date()) == "2026-11-10"


def test_headlines_fallback():
    from altinfo.sources import headlines as hl
    xml = ('<?xml version="1.0"?><rss><channel><item><title>Copper prices surge on mine disruption - Reuters</title>'
           '<link>https://news.google.com/rss/articles/a</link><pubDate>Tue, 10 Nov 2026 14:00:00 GMT</pubDate>'
           '<source url="https://reuters.com">Reuters</source></item></channel></rss>')
    items = hl.parse_rss(xml)
    assert items[0]["title"] == "Copper prices surge on mine disruption" and items[0]["domain"] == "Reuters"
    att = engine._attention_headlines(items)
    assert att["available"] and att["mode"] == "headlines" and att["headlines"][0]["url"].startswith("https://")


def test_cache_and_history():
    store.cache_put("t", "k", {"a": 1})
    assert store.cache_get("t", "k", 60)[0] == {"a": 1}
    assert store.cache_get("t", "k", -1)[0] is None            # expired
    assert store.cache_get("t", "k", None)[0] == {"a": 1}      # but still there as a fallback
    store.put_series("X", "price", [("2026-11-09", 1.0), ("2026-11-10", 2.0)])
    assert [p["v"] for p in store.get_series("X", "price")] == [1.0, 2.0]


def test_full_analysis_has_every_part():
    if not HAVE_RAW:
        return
    seen = []
    r = engine.analyze("brent", progress=lambda i, s: seen.append(i), offline=True)
    assert seen == [0, 1, 2, 3]
    for part in ("evidence", "expectations", "priced_in", "gap", "confidence", "risks", "conclusion", "history", "sources"):
        assert part in r
    assert r["headline"]["basis"] == "evidence" and abs(r["headline"]["ours"] - 0.6167) < 1e-3
    assert 5 <= r["confidence"]["score"] <= 95 and r["conclusion"]["text"]
    assert len(engine.analyze("brent", offline=True)["history"]["analyses"]) >= 2   # every run is stored


def test_api_never_exposes_secrets():
    sys.path.insert(0, os.path.join(ROOT, "server"))
    os.environ["EIA_API_KEY"] = "SECRET-KEY-123"
    import importlib
    from altinfo import config
    importlib.reload(config)
    import app as server
    c = server.app.test_client()
    assert "SECRET-KEY-123" not in c.get("/api/health").get_data(as_text=True)
    assert "SECRET-KEY-123" not in c.get("/").get_data(as_text=True)
    assert c.get("/files/README.md").status_code == 404 and c.get("/static/../altinfo/config.py").status_code == 404
    assert c.post("/api/analyze", json={"q": ""}).status_code == 400
    assert "script-src 'self'" in c.get("/").headers["Content-Security-Policy"]



def test_track_record_watchlist():
    sys.path.insert(0, os.path.join(ROOT, "server"))
    import app as server
    c = server.app.test_client()
    keys = [w["key"] for w in c.get("/api/watchlist").get_json()]
    assert keys[:2] == ["NVDA", "BRENT"]                     # the two report calls are there from the start
    assert c.post("/api/watchlist", json={"q": "zzzzqq"}).status_code == 404
    if HAVE_RAW:
        assert c.post("/api/watchlist", json={"q": "copper"}).get_json()["key"] == "COPPER"
        assert "COPPER" in [w["key"] for w in c.get("/api/watchlist").get_json()]
        c.delete("/api/watchlist/COPPER")
    c.delete("/api/watchlist/NVDA")
    assert "NVDA" not in [w["key"] for w in c.get("/api/watchlist").get_json()]
    assert c.get("/api/calls").get_json()["calls"][0]["outcome"] is None


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
