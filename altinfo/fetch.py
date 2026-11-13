"""Integration layer: one door to every source, with cache, offline fallback and a status report.

The engine never calls a source client directly. It asks a `Fetcher` for prices, markets, weather and so on; the
fetcher answers from the cache when the data is fresh, downloads when it is not, and falls back to the last copy
(stale cache, then the files of scripts/fetch_data.py) when a source cannot be reached. Each answer is recorded in
`fetcher.status`, which the API returns so the page can say what is live and what is not.

Adding a source = one client in altinfo/sources plus one method here. Nothing else changes.
"""
import io
import re
import time
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from . import config, store
from .sources import http

LABEL = {"prices": "Market prices", "kalshi": "Kalshi", "polymarket": "Polymarket", "usgs": "Earthquakes (USGS)",
         "firms": "Fires (NASA)", "weather": "Weather", "eia": "Oil stocks (EIA)", "fundamentals": "Analyst consensus",
         "curve": "Futures curve", "news": "News (GDELT)", "headlines": "Headlines (Google News, Yahoo)", "profile": "Company profile", "earnings": "Earnings history"}
DOWN = {}            # host -> time until which it is skipped: a blocked site is tried once, not on every request
DOWN_FOR = 180       # seconds
DOWN_WHY = {}        # host -> the error that put it in DOWN, repeated while it is skipped
RANK = {"live": 0, "cache": 0, "stale": 1, "file": 1, "snapshot": 1, "missing": 2, "failed": 3}


def _rec(df):
    return df.to_json(orient="split", date_format="iso") if df is not None else None


def _df(payload):
    # dtype=False: keep long ids (Polymarket tokens) as text; dates are parsed by each method
    return pd.read_json(io.StringIO(payload), orient="split", dtype=False, convert_dates=False) if payload else None


class Fetcher:
    def __init__(self, offline=False, on_source=None):
        self.offline = offline          # True: never touch the network (tests, demos without connection)
        self.status = {}                # source -> {"state", "age_min", "note"}
        self.on_source = on_source      # called with the name of each source being downloaded (loading screen)

    # ------------------------------------------------------------------ core
    def _note(self, source, state, age=None, note=""):
        old = self.status.get(source)
        if old is None or RANK[state] >= RANK[old["state"]]:  # keep the worst state seen for the source
            self.status[source] = {"source": source, "label": LABEL.get(source, source), "state": state,
                                   "age_min": None if age is None else round(age / 60), "note": note}

    def _get(self, source, key, loader, fallback=None, ttl=None, hosts=(), optional=False):
        """Fresh cache -> download -> stale cache -> local file. Returns a DataFrame/Series payload or None."""
        ttl = config.TTL.get(source, 600) if ttl is None else ttl
        hit, age = store.cache_get(source, key, ttl)
        if hit is not None:
            self._note(source, "cache", age)
            return _df(hit)
        err = ""
        down = [h for h in hosts if DOWN.get(h, 0) > time.time()]
        if down:
            err = f"{down[0]} did not answer a moment ago ({DOWN_WHY.get(down[0], '')})"[:200]
        if not self.offline and not down:
            if self.on_source:
                self.on_source(LABEL.get(source, source))
            for h in hosts:
                http.LAST_ERROR.pop(h, None)
            try:
                df = loader()
                bad = [h for h in hosts if h in http.LAST_ERROR]
                if df is not None and len(df) and not bad:
                    store.cache_put(source, key, _rec(df))
                    self._note(source, "live", 0)
                    return df
                err = http.LAST_ERROR.get(bad[0], "") if bad else "no data returned"
                for h in bad:
                    DOWN[h] = time.time() + (1800 if "429" in str(err) else DOWN_FOR)   # rate limited: leave it alone longer
                    DOWN_WHY[h] = err
                if df is not None and not bad:      # the source answered: there is simply nothing for this key
                    store.cache_put(source, key, _rec(df))
                    self._note(source, "live", 0)
                    return df
            except Exception as e:  # a source must never take the analysis down
                err = f"{type(e).__name__}: {e}"[:160]
        old, age = store.cache_get(source, key, None)
        if old is not None:
            self._note(source, "stale", age, err)
            return _df(old)
        if fallback is not None:
            try:
                df = fallback()
                if df is not None and len(df):
                    self._note(source, "file", None, err or "offline")
                    return df
            except Exception:
                pass
        if not optional:  # optional sources (company profile, earnings history) do not count as problems
            self._note(source, "failed" if err else "missing", None, err)
        return None

    @staticmethod
    def _csv(name, **kw):
        f = config.RAW / name
        return pd.read_csv(f, **kw) if f.exists() else None

    # ------------------------------------------------------------------ prices
    def prices(self, ticker, days=420, optional=False):
        """Daily closes of one ticker (Series indexed by date)."""
        from .sources import yahoo
        end = pd.Timestamp.now("UTC").tz_localize(None).normalize() + pd.Timedelta(days=1)
        start = end - pd.Timedelta(days=days)

        def load():
            s = yahoo.prices(ticker, start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
            return s.rename("close").rename_axis("date").reset_index() if len(s) else None

        def file():
            p = self._csv("prices.csv")
            if p is None:
                return None
            p = p[p.ticker == ticker].copy()
            p["date"] = pd.to_datetime(p["date"], format="mixed")
            return p[["date", "close"]]
        df = self._get("prices", ticker, load, file, optional=optional)
        if df is None or df.empty:
            return pd.Series(dtype=float, name=ticker)
        s = pd.Series(df["close"].values, index=pd.to_datetime(df["date"]).dt.tz_localize(None).dt.normalize(), name=ticker)
        return s.dropna().sort_index()

    def prices_many(self, tickers, optional=False):
        with ThreadPoolExecutor(6) as ex:
            return dict(zip(tickers, ex.map(lambda t: self.prices(t, optional=optional), tickers)))

    # ------------------------------------------------------------------ prediction markets
    def kalshi_markets(self, series):
        """Open contracts of one Kalshi series."""
        from .sources import kalshi

        def load():
            m = kalshi.markets(series_ticker=series, status="open")
            return m.assign(series=series) if len(m) else pd.DataFrame(columns=["ticker", "title", "series"])

        def file():
            k = self._csv("kalshi_markets.csv")
            return k[k.series == series] if k is not None else None
        df = self._get("kalshi", f"markets:{series}", load, file, hosts=("api.elections.kalshi.com",))
        return df if df is not None else pd.DataFrame()

    def kalshi_catalog(self):
        """Every Kalshi series (ticker, title), downloaded once a day and searched locally for each ticker."""
        from .sources import kalshi

        def load():
            cats = ("Economics", "Commodities", "Financials", "Companies", "World", "Politics", "Climate and Weather")
            frames = [kalshi.all_series(c) for c in cats] + [kalshi.all_series()]
            frames = [x for x in frames if len(x)]
            if not frames:
                return None
            df = pd.concat(frames, ignore_index=True).drop_duplicates("ticker")
            return df[["ticker", "title"]].fillna("")

        def file():
            k = self._csv("kalshi_markets.csv")
            return k.groupby("series").title.first().reset_index().rename(columns={"series": "ticker"}) if k is not None else None
        df = self._get("kalshi", "catalog", load, file, ttl=config.TTL["resolver"], hosts=("api.elections.kalshi.com",), optional=True)
        return df if df is not None else pd.DataFrame(columns=["ticker", "title"])

    def kalshi_find(self, keywords):
        """Series whose title or ticker contains one of the keywords as a whole word."""
        cat = self.kalshi_catalog()
        if cat.empty:
            return cat
        text = cat["title"].astype(str) + " " + cat["ticker"].astype(str)
        hit = pd.Series(False, index=cat.index)
        for k in keywords:
            hit |= text.str.contains(rf"\b{re.escape(k)}\b", case=False, regex=True)
            if k.isalpha() and k.isupper() and 3 <= len(k) <= 5:   # tickers are glued into series codes: KXNVDAMENTION
                hit |= cat["ticker"].astype(str).str.upper().str.contains("KX" + k, regex=False)
        return cat[hit]

    def kalshi_candles(self, tickers, days=120):
        """Daily price history of Kalshi contracts: date, ticker, price, volume."""
        from .sources import kalshi
        tickers = sorted(tickers)
        if not tickers:
            return pd.DataFrame(columns=["date", "ticker", "price", "volume"])
        end = pd.Timestamp.now("UTC").tz_localize(None).normalize() + pd.Timedelta(days=1)
        start = end - pd.Timedelta(days=days)

        def file():
            c = self._csv("kalshi_candles.csv", parse_dates=["date"])
            return c[c.ticker.isin(tickers)] if c is not None else None
        df = self._get("kalshi", "candles:" + ",".join(tickers), lambda: kalshi.candles(
            tickers, start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"), archive=False), file,
            ttl=config.TTL["curve"], hosts=("api.elections.kalshi.com",), optional=True)
        if df is None:
            return pd.DataFrame(columns=["date", "ticker", "price", "volume"])
        df["date"] = pd.to_datetime(df["date"])
        return df

    def poly_markets(self, query, pattern=None):
        """Open Polymarket markets for a free text query, optionally filtered by a regular expression."""
        from .sources import polymarket

        def load():
            t = polymarket.markets_table(polymarket.search(query))
            return t.drop_duplicates("market_slug") if len(t) else pd.DataFrame(columns=["question"])

        def file():
            return self._csv("polymarket_markets.csv", dtype={"yes_token": str})
        df = self._get("polymarket", f"search:{query.lower()}", load, file, hosts=("gamma-api.polymarket.com",))
        if df is None or df.empty or "question" not in df:
            return pd.DataFrame()
        df = df[df["closed"] != True] if "closed" in df else df  # noqa: E712
        if pattern:
            df = df[df["question"].str.contains(pattern, case=False, na=False, regex=True)]
        return df

    def poly_all(self, queries, pattern=None):
        """Every open Polymarket market found by several queries (name, ticker, related words), without duplicates."""
        frames = [self.poly_markets(q, pattern) for q in dict.fromkeys(q for q in queries if q)]
        frames = [x for x in frames if len(x)]
        if not frames:
            return pd.DataFrame()
        df = pd.concat(frames, ignore_index=True)
        return df.drop_duplicates("market_slug") if "market_slug" in df else df

    def news(self, query, cache_only=False):
        """News attention: daily volume and tone over 3 months and the latest headlines (GDELT). None if unreachable.
        cache_only: answer from saved copies only (the analysis never waits for GDELT; the page asks for news separately)."""
        from .sources import gdelt
        host = ("api.gdeltproject.org",)
        if cache_only:
            got = {k: store.cache_get("news", f"{k}:{query}", 6 * 3600)[0] for k in ("vol", "tone", "art")}
            if not got["vol"]:
                return None
            vol, ton, art = (_df(got[k]) if got[k] else None for k in ("vol", "tone", "art"))
            ser = lambda d: pd.Series(d["v"].astype(float).values, index=pd.to_datetime(d["t"])).sort_index() if d is not None and len(d) else pd.Series(dtype=float)  # noqa: E731
            return {"volume": ser(vol), "tone": ser(ton), "articles": art.to_dict("records") if art is not None and len(art) else []}
        vol = self._get("news", "vol:" + query, lambda: gdelt.volume(query).rename("v").rename_axis("t").reset_index(),
                        hosts=host, ttl=6 * 3600)
        if vol is None or vol.empty:
            store.cache_clear_key("news", "vol:" + query)   # an empty answer is not kept: try again next time
            if vol is not None:
                self._note("news", "missing", None, "GDELT returned no coverage: " + gdelt.LAST_RAW.get("timelinevol", "")[:120])
            return None
        ton = self._get("news", "tone:" + query, lambda: gdelt.tone(query).rename("v").rename_axis("t").reset_index(),
                        hosts=host, ttl=3 * 3600, optional=True)
        art = self._get("news", "art:" + query, lambda: pd.DataFrame(gdelt.articles(query)), hosts=host, ttl=3 * 3600,
                        optional=True)
        ser = lambda d: pd.Series(d["v"].astype(float).values, index=pd.to_datetime(d["t"])).sort_index() if d is not None and len(d) else pd.Series(dtype=float)  # noqa: E731
        return {"volume": ser(vol), "tone": ser(ton), "articles": art.to_dict("records") if art is not None and len(art) else []}

    def headlines(self, query, ticker, cache_only=False):
        """Latest headlines from Google News (last 7 days) and Yahoo Finance, without duplicates, newest first."""
        from .sources import headlines as hl
        key = f"{query}|{ticker}"
        if cache_only:
            hit = store.cache_get("headlines", key, 3600)[0]
            return _df(hit).to_dict("records") if hit else None

        def load():
            items = hl.google_news(query) + hl.yahoo_news(ticker)
            seen, out = set(), []
            for x in items:
                k = re.sub(r"\W+", " ", x["title"].lower()).strip()[:80]
                if k and k not in seen:
                    seen.add(k)
                    out.append(x)
            df = pd.DataFrame(out, columns=["title", "url", "domain", "time"])
            return df.sort_values("time", ascending=False, na_position="last") if len(df) else df
        df = self._get("headlines", key, load, ttl=3600, hosts=("news.google.com",))
        return df.to_dict("records") if df is not None and len(df) else None

    def poly_history(self, market_slug, token):
        """Daily probability of one Polymarket outcome (Series indexed by day)."""
        from .sources import polymarket

        def load():
            s = polymarket.daily_close(polymarket.history(token))
            return s.rename("prob").rename_axis("date").reset_index() if len(s) else None

        def file():
            h = self._csv("polymarket_history.csv", parse_dates=["date"])
            return h[h.market_slug == market_slug][["date", "prob"]] if h is not None else None
        df = self._get("polymarket", f"history:{market_slug}", load, file, ttl=config.TTL["curve"], hosts=("clob.polymarket.com",),
                       optional=True)
        if df is None or df.empty:
            return pd.Series(dtype=float)
        return pd.Series(df["prob"].values, index=pd.to_datetime(df["date"]).dt.tz_localize(None)).sort_index()

    # ------------------------------------------------------------------ physical feeds
    def quakes(self):
        from .sources import usgs
        df = self._get("usgs", "m4.5_month", lambda: usgs.earthquakes("4.5", "month"), lambda: self._csv("usgs_quakes.csv"),
                       hosts=("earthquake.usgs.gov",))
        if df is not None and len(df):
            df["time"] = pd.to_datetime(df["time"], utc=True)
        return df

    def fires(self, sites):
        """Fires of the last 7 days within 300 km of the given sites (the world file is large, so it is filtered once)."""
        from .monitors import km_between
        from .sources import firms

        def load():
            f = firms.fires("7d")
            if f.empty:
                return None
            from .coverage import COVERAGE
            every = [s for v in COVERAGE.values() for s in v["sites"]] + list(sites)
            keep = pd.Series(False, index=f.index)
            for s in every:
                keep |= (f.lat.sub(s["lat"]).abs() < 3) & (f.lon.sub(s["lon"]).abs() < 4)
            f = f[keep]
            near = [min(km_between(r.lat, r.lon, s["lat"], s["lon"]) for s in every) <= 300 for r in f.itertuples()]
            return f[near] if len(f) else f
        df = self._get("firms", "7d", load, lambda: self._csv("firms_fires.csv"), hosts=("firms.modaps.eosdis.nasa.gov",))
        if df is not None and len(df):
            df["time"] = pd.to_datetime(df["time"], utc=True)
        return df

    def weather(self, regions):
        """Daily rain and temperature since 2015 for growing regions: {name: (lat, lon)} -> long DataFrame."""
        from .sources import weather
        end = (pd.Timestamp.now() - pd.Timedelta(days=6)).strftime("%Y-%m-%d")
        frames = []
        for name, (la, lo) in regions.items():
            def file(n=name):
                w = self._csv("weather.csv", parse_dates=["date"])
                return w[w.region == n] if w is not None else None
            df = self._get("weather", name, lambda la=la, lo=lo, n=name: weather.daily(la, lo, "2015-01-01", end).assign(region=n),
                           file, hosts=("archive-api.open-meteo.com",))
            if df is not None and len(df):
                df["date"] = pd.to_datetime(df["date"])
                frames.append(df)
        return pd.concat(frames, ignore_index=True) if frames else None

    def eia(self):
        """Weekly US petroleum summary and the EIA Brent outlook. Live with a key, else the snapshot figures."""
        import json
        from .sources import eia
        snap = json.load(open(config.SNAPSHOT))["brent"]["real"]
        out = {"live": False, "weekly": dict(snap["eia_week_to_2026-10-30"], week_ending="2026-10-30"),
               "outlook": snap["eia_steo_2026-10-06"], "outlook_as_of": "6 Oct 2026", "stocks_history": []}
        if not config.EIA_API_KEY:
            self._note("eia", "snapshot", None, "no EIA_API_KEY in .env: figures of the 9 Nov report")
            return out
        wk = self._get("eia", "weekly", lambda: eia.weekly_petroleum(config.EIA_API_KEY).rename_axis("date").reset_index(),
                       hosts=("api.eia.gov",))
        if wk is not None and len(wk):
            wk = wk.set_index(pd.to_datetime(wk["date"])).drop(columns="date")
            s = eia.summary(wk)
            if s:
                out.update(live=True, weekly={k: (None if v is None or v != v else float(v) if not isinstance(v, str) else v)
                                              for k, v in s.items()})
                c = wk["commercial_crude_kb"].dropna().iloc[-104:] / 1000
                out["stocks_history"] = [{"t": d.strftime("%Y-%m-%d"), "v": round(float(v), 1)} for d, v in c.items()]
        st = self._get("eia", "steo", lambda: eia.steo_brent(config.EIA_API_KEY).rename("value").rename_axis("date").reset_index(),
                       hosts=("api.eia.gov",))
        if st is not None and len(st):
            s = pd.Series(st["value"].values, index=pd.to_datetime(st["date"]))
            now = pd.Timestamp.now()
            q = s[(s.index.year == now.year) & (s.index.quarter == now.quarter)]
            out["outlook"] = {f"Brent {now.quarter}Q{str(now.year)[-2:]}, $/b": round(float(q.mean()), 0),
                              f"Brent {now.year} average, $/b": round(float(s[s.index.year == now.year].mean()), 0),
                              f"Brent {now.year + 1} average, $/b": round(float(s[s.index.year == now.year + 1].mean()), 0)}
            out["outlook_as_of"] = "latest release"
        return out

    # ------------------------------------------------------------------ fundamentals
    def fundamentals(self, tickers):
        from .sources import yahoo
        key = ",".join(sorted(tickers))

        def file():
            f = self._csv("fundamentals.csv")
            return f[f.ticker.isin(tickers)] if f is not None else None
        return self._get("fundamentals", key, lambda: yahoo.fundamentals(list(tickers))[0], file, optional=True)

    def curve(self, root):
        from .sources import yahoo

        def load():
            con = yahoo.contract_tickers(root, pd.Timestamp.now())
            w = yahoo.prices_many([t for t, _ in con], (pd.Timestamp.now() - pd.Timedelta(days=100)).strftime("%Y-%m-%d"),
                                  (pd.Timestamp.now() + pd.Timedelta(days=1)).strftime("%Y-%m-%d"))
            rows = [{"date": d.strftime("%Y-%m-%d"), "root": root, "contract": t, "month": m, "close": v}
                    for t, m in con if w is not None and t in w for d, v in w[t].dropna().items()]
            return pd.DataFrame(rows) if rows else None

        def file():
            c = self._csv("futures_curve.csv")
            return c[c.root == root] if c is not None else None
        return self._get("curve", root, load, file, optional=True)

    def profile(self, ticker):
        """Name and type of a ticker the registry does not know (Yahoo). Returns a dict or None."""
        def load():
            import yfinance as yf
            i = yf.Ticker(ticker).info or {}
            if not (i.get("shortName") or i.get("longName")):
                return None
            return pd.DataFrame([{"name": i.get("shortName") or i.get("longName"), "type": i.get("quoteType", ""),
                                  "sector": i.get("sector") or i.get("category") or "", "country": i.get("country", "")}])
        df = self._get("profile", ticker, load, ttl=config.TTL["resolver"], optional=True)
        return df.iloc[0].to_dict() if df is not None and len(df) else None

    def earnings_history(self, ticker):
        """Past quarters with the EPS estimate and the reported EPS (Yahoo): date, estimate, actual."""
        def load():
            import yfinance as yf
            e = yf.Ticker(ticker).get_earnings_dates(limit=16)
            if e is None or e.empty:
                return None
            e = e.dropna(subset=["Reported EPS"]).reset_index()
            return pd.DataFrame({"date": pd.to_datetime(e.iloc[:, 0]).dt.tz_localize(None), "estimate": e["EPS Estimate"],
                                 "actual": e["Reported EPS"]})
        df = self._get("earnings", ticker, load, ttl=config.TTL["fundamentals"], optional=True)
        if df is not None and len(df):
            df["date"] = pd.to_datetime(df["date"])
        return df


def started():
    return time.time()
