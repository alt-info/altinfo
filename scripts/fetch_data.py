"""Download everything the notebooks need into data/raw. Public endpoints, no API keys.

    python scripts/fetch_data.py            # full download (about 2 to 4 minutes)
    python scripts/fetch_data.py --quick    # prices and preset markets only

Outputs (data/raw)
  prices.csv               date, ticker, close             Yahoo Finance daily adjusted closes
  kalshi_fed.csv           date, meeting, outcome, price   FOMC decision markets, daily
  kalshi_markets.csv       snapshot of Brent, WTI, Hormuz and NVIDIA related Kalshi markets
  kalshi_candles.csv       daily history of those markets
  polymarket_markets.csv   markets found by slug or keyword search, with current price and volume
  polymarket_history.csv   date, market_slug, prob (daily close, US Eastern)
  futures_curve.csv        date, root, contract, month, close   next 12 Brent and WTI contracts
  fundamentals.csv         multiples, consensus and price targets of NVIDIA and its peers
  eps_annual.csv, monthly_prices.csv   for multiples against history
  weather.csv              daily rain and temperature in the growing regions since 2015 (Open-Meteo)
  firms_fires.csv          active fires of the last 7 days within 300 km of a covered site (NASA FIRMS)
  fetch_log.txt            what was found, for checking
"""
import os
import sys
from datetime import datetime, timezone

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from altinfo.sources import kalshi, polymarket, usgs, yahoo  # noqa: E402

OUT = os.path.join(ROOT, "data", "raw")
os.makedirs(OUT, exist_ok=True)
QUICK = "--quick" in sys.argv
REUSE = "--reuse" in sys.argv  # keep prices.csv if it already exists
START, END = "2024-10-01", (pd.Timestamp.now("UTC") + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
log = []


def say(msg):
    print(msg)
    log.append(msg)


# 0. Connectivity check: stop early with a clear message if the sites cannot be reached ---------
from altinfo.sources.http import get_json, LAST_ERROR  # noqa: E402
checks = {"Kalshi": "https://api.elections.kalshi.com/trade-api/v2/series/KXFEDDECISION",
          "Polymarket": "https://gamma-api.polymarket.com/events?limit=1"}
ok = {k: get_json(u, tries=1) is not None for k, u in checks.items()}
say("connectivity: " + ", ".join(f"{k} {'OK' if v else 'FAILED'}" for k, v in ok.items()))
if not any(ok.values()) and yahoo.prices_many(["SPY"], "2026-10-01", END) is None:
    sys.exit("No site reachable. Errors: " + "; ".join(f"{h}: {e}" for h, e in LAST_ERROR.items()) +
             "\nIf it says CERTIFICATE_VERIFY_FAILED run:  pip install certifi  and then"
             "\n  export SSL_CERT_FILE=$(python3 -m certifi)   and retry.")

# 1. Prices ----------------------------------------------------------------------------
TICKERS = ["NVDA", "SMH", "AMD", "TSM", "MU", "BZ=F", "CL=F", "SPY", "QQQ", "IWM", "TLT", "IEF", "HYG", "GLD",
           "USO", "XLE", "ITA", "JETS", "XLF", "EEM", "FXI", "EWT", "EWJ", "VGK", "UUP", "BTC-USD", "^VIX", "^TNX",
           "HG=F", "GC=F", "NG=F", "ZC=F", "ZW=F", "ZS=F", "KC=F", "SB=F", "FCX", "SCCO", "TECK", "COPX", "NEM",
           "AVGO", "QCOM", "INTC", "DE", "ADM", "BG", "CTVA", "SBUX", "PRY.MI"]
have = lambda name: REUSE and os.path.exists(os.path.join(OUT, name))
old = pd.read_csv(os.path.join(OUT, "prices.csv")) if have("prices.csv") else pd.DataFrame(columns=["date", "ticker", "close"])
todo = [t for t in TICKERS if t not in set(old["ticker"])]  # with --reuse only the missing tickers are downloaded
frames = [old] if len(old) else []
wide = yahoo.prices_many(todo, START, END) if todo else None  # one batch call through yfinance
for t in todo:
    s = wide[t].dropna() if wide is not None and t in wide else pd.Series(dtype=float)
    if s.empty:  # fallback: direct chart endpoint, one ticker at a time
        s = yahoo.prices(t, START, END)
    say(f"prices {t}: {len(s)} days")
    frames.append(s.rename("close").rename_axis("date").reset_index().assign(ticker=t))
allp = pd.concat(frames)[["date", "ticker", "close"]]
allp["date"] = pd.to_datetime(allp["date"], format="mixed").dt.strftime("%Y-%m-%d")
allp.to_csv(os.path.join(OUT, "prices.csv"), index=False)
say(f"prices: {len(TICKERS) - len(todo)} reused, {len(todo)} downloaded")

# 1b. Earthquakes near mines (USGS, free) ------------------------------------------------------
q = usgs.earthquakes("4.5", "month")
q.to_csv(os.path.join(OUT, "usgs_quakes.csv"), index=False)
say(f"usgs earthquakes M4.5+ last 30 days: {len(q)}")

# 2. Kalshi: FOMC decision markets -----------------------------------------------------------
MEETINGS = ["25JUL", "25SEP", "25OCT", "25DEC", "26JAN", "26MAR", "26APR", "26JUN", "26JUL", "26SEP", "26OCT",
            "26DEC", "27JAN", "27MAR"]
OUTCOMES = ["C26", "C25", "H0", "H25", "H26"]
tick = [f"KXFEDDECISION-{m}-{o}" for m in MEETINGS for o in OUTCOMES]
fed = kalshi.candles(tick, "2025-06-01", END)
fed["meeting"] = fed["ticker"].str.split("-").str[1]
fed["outcome"] = fed["ticker"].str.split("-").str[2]
fed[["date", "meeting", "outcome", "price", "volume", "open_interest"]].to_csv(os.path.join(OUT, "kalshi_fed.csv"), index=False)
say(f"kalshi fed: {len(fed)} candles, {fed.ticker.nunique()} contracts")

# 3. Kalshi: Brent, WTI, Hormuz, NVIDIA ------------------------------------------------------------
if not QUICK:
    ser = kalshi.find_series(["brent", "wti", "crude", "oil price", "hormuz", "nvidia", "nvda", "copper", "gold",
                              "corn", "wheat", "soybean", "coffee", "sugar"])
    say(f"kalshi series matched: {len(ser)} -> {', '.join(ser.ticker.head(25))}")
    snaps = []
    for t in ser.ticker:
        m = kalshi.markets(series_ticker=t, status="open")
        if len(m):
            snaps.append(m.assign(series=t))
    snap = pd.concat(snaps, ignore_index=True) if snaps else pd.DataFrame()
    snap.to_csv(os.path.join(OUT, "kalshi_markets.csv"), index=False)
    say(f"kalshi open markets in those series: {len(snap)}")
    # daily history only for the series used in the previews (hourly and 15 minute series are skipped)
    KEEP = ["KXBRENTMON", "KXBRENTW", "KXBRENTD", "KXHORMUZNORM", "KXHORMUZWEEKLY", "KXMAXSHIPSHORMUZ",
            "KXEARNINGSMENTIONNVDA", "KXNVDAMENTION", "KXWTIMAX", "KXWTIMIN"]
    if len(snap):
        sel = snap[snap["series"].isin(KEEP)]["ticker"].tolist()
        say(f"kalshi candles for {len(sel)} markets in {', '.join(KEEP)}")
        c = kalshi.candles(sel, "2026-06-01", END, archive=False)
        c.to_csv(os.path.join(OUT, "kalshi_candles.csv"), index=False)
        say(f"kalshi candles: {len(c)}")

# 4. Polymarket ----------------------------------------------------------------------------
SLUGS = {
    "us_invades_iran": "will-the-us-invade-iran-before-2027",
    "iran_regime_falls": "will-the-iranian-regime-fall-by-the-end-of-2026",
    "hormuz_normal": "strait-of-hormuz-traffic-returns-to-normal-by-december-31",
    "china_invades_taiwan": "will-china-invade-taiwan-before-2027",
    "us_recession_2026": "us-recession-by-end-of-2026",
}
QUERIES = [] if QUICK else ["nvidia earnings", "nvidia", "nvda", "wti", "crude oil", "brent", "iran ceasefire",
                            "hormuz", "iran agreement", "copper", "gold"]
events, keys = [], {}
for key, slug in SLUGS.items():
    e = polymarket.event(slug)
    if e:
        events.append(e)
        keys[slug] = key
    say(f"polymarket {key}: {'found' if e else 'NOT FOUND'}")
for q in QUERIES:
    found = polymarket.search(q)
    events += found
    say(f"polymarket search '{q}': {len(found)} events")
mk = polymarket.markets_table(events).drop_duplicates("market_slug")
mk["key"] = mk["event_slug"].map(keys)
mk = mk[(mk["key"].notna()) | (mk["closed"] != True)]  # noqa: E712
mk.to_csv(os.path.join(OUT, "polymarket_markets.csv"), index=False)
take = pd.concat([mk[mk.key.notna()], mk[mk.key.isna()].sort_values("volume", ascending=False).head(60)])
hist = []
for r in take.itertuples():
    if not r.yes_token:
        continue
    h = polymarket.daily_close(polymarket.history(r.yes_token))
    hist.append(pd.DataFrame({"date": h.index, "market_slug": r.market_slug,
                              "key": r.key if isinstance(r.key, str) else "", "prob": h.values}))
ph = pd.concat(hist, ignore_index=True) if hist else pd.DataFrame(columns=["date", "market_slug", "key", "prob"])
ph.to_csv(os.path.join(OUT, "polymarket_history.csv"), index=False)
say(f"polymarket: {len(mk)} markets listed, history for {ph.market_slug.nunique()} ({len(ph)} points)")

# 5. Futures curves: next 12 Brent and WTI contracts (Yahoo) ------------------------------------
from altinfo.coverage import COVERAGE  # noqa: E402
from altinfo.monitors import km_between  # noqa: E402
from altinfo.sources import firms, weather  # noqa: E402

if not have("futures_curve.csv"):
    rows = []
    for root in ("BZ", "CL"):
        con = yahoo.contract_tickers(root, pd.Timestamp.now())
        w = yahoo.prices_many([t for t, _ in con], "2026-08-01", END)
        for t, month in con:
            if w is not None and t in w:
                s_ = w[t].dropna()
                rows += [{"date": d.strftime("%Y-%m-%d"), "root": root, "contract": t, "month": month, "close": v} for d, v in s_.items()]
    fc = pd.DataFrame(rows, columns=["date", "root", "contract", "month", "close"])
    fc.to_csv(os.path.join(OUT, "futures_curve.csv"), index=False)
    say(f"futures curve: {fc.contract.nunique()} contracts, {len(fc)} prices")

# 6. Fundamentals: multiples, consensus, price targets (Yahoo) -------------------------------------
if not have("fundamentals.csv"):
    snap_f, eps, mon = yahoo.fundamentals(["NVDA", "AMD", "AVGO", "TSM", "MU", "QCOM", "INTC"])
    if snap_f is not None:
        snap_f.to_csv(os.path.join(OUT, "fundamentals.csv"), index=False)
        eps.to_csv(os.path.join(OUT, "eps_annual.csv"), index=False)
        mon.to_csv(os.path.join(OUT, "monthly_prices.csv"), index=False)
        say(f"fundamentals: {len(snap_f)} companies, {len(eps)} annual EPS, {len(mon)} monthly prices")

# 7. Weather in the growing regions (Open-Meteo, free) ----------------------------------------------
if not have("weather.csv"):
    regions = {}
    for v in COVERAGE.values():
        for s_ in v["sites"]:
            if s_["role"] == "Growing region":
                regions[s_["site"]] = (s_["lat"], s_["lon"])
    wx = []
    end_w = (pd.Timestamp.now() - pd.Timedelta(days=6)).strftime("%Y-%m-%d")  # reanalysis lags about 5 days
    for name, (la, lo) in regions.items():
        d = weather.daily(la, lo, "2015-01-01", end_w)
        wx.append(d.assign(region=name))
        say(f"weather {name}: {len(d)} days")
    pd.concat(wx, ignore_index=True).to_csv(os.path.join(OUT, "weather.csv"), index=False)

# 8. Active fires near covered sites (NASA FIRMS, free) ---------------------------------------------
f7 = firms.fires("7d")
sites = [s_ for v in COVERAGE.values() for s_ in v["sites"]]
if len(f7):
    import numpy as np
    keep = np.zeros(len(f7), dtype=bool)
    for s_ in sites:  # cheap box filter first, exact distance after
        box = (f7.lat.sub(s_["lat"]).abs() < 3) & (f7.lon.sub(s_["lon"]).abs() < 4)
        keep |= box.values
    f7 = f7[keep]
    f7 = f7[[min(km_between(r.lat, r.lon, s_["lat"], s_["lon"]) for s_ in sites) <= 300 for r in f7.itertuples()]]
f7.to_csv(os.path.join(OUT, "firms_fires.csv"), index=False)
say(f"nasa firms: {len(f7)} fires in the last 7 days within 300 km of a covered site")

stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
with open(os.path.join(OUT, "fetch_log.txt"), "w") as f:
    f.write(f"Downloaded {stamp}\n" + "\n".join(log) + "\n")
print(f"\nDone. Files in {OUT}")
