<img src="assets/altinfo_logo.svg" alt="ALT/INFO" width="320">

# Code behind the previews

Python code for the ALT/INFO alternative information platform. It reproduces the numbers and charts
of the two sample previews of 9 November 2026 (**NVIDIA Q3 FY2027 Pre-Earnings Preview** and
**Brent Crude Pre-Event Preview**) and estimates how asset prices react to prediction market odds.

## Quick start

```bash
pip install -r requirements.txt
python tests/test_core.py          # 13 unit tests, about 2 seconds
python scripts/fetch_data.py       # download live data into data/raw (3 to 6 minutes)
                                   # --reuse keeps prices already downloaded
                                   # on networks that block Kalshi/Polymarket (e.g. some UK campus Wi-Fi)
                                   # run notebooks/00_fetch_in_colab.ipynb in Google Colab instead
jupyter notebook notebooks/        # open a notebook and Run All
```

Without `data/raw` the notebooks run in **snapshot mode** on the figures printed in the previews
(`data/snapshot_2026-11-09.json`). After `fetch_data.py` they switch to **live mode** automatically.
Notebook 03 needs live data.

## The app: type a ticker, get the analysis

```bash
python server/app.py               # then open http://127.0.0.1:8000
```

Type a ticker (NVDA, AAPL) or a commodity (Brent, copper). The page shows the loading steps, then the analysis:
what the observable data show, what the market expects, how much is already in the price, the gap, the confidence,
the risks and a conclusion in plain words. Ten names are covered in depth; any other ticker gets a basic analysis.

| Layer | File | Job |
|---|---|---|
| Interface | `web/index.html`, `web/app.js`, `web/style.css` | Search box, loading and error states, charts and tables. Talks only to `/api` |
| Backend | `server/app.py` | HTTP routes and background jobs, no analysis logic |
| Data retrieval | `altinfo/fetch.py`, `altinfo/sources/` (Kalshi, Polymarket, Yahoo, EIA, GDELT, USGS, NASA, Open-Meteo) | One door to every source, with cache, fallback and a status per source |
| Ticker matching | `altinfo/resolver.py`, `altinfo/coverage.py` | Ticker to asset, markets, events and places; drops unrelated markets |
| Normalisation | `altinfo/normalize.py` | One schema for Kalshi and Polymarket contracts and for time series |
| Analysis | `altinfo/engine.py` | Orchestrates `gap`, `valuation`, `earnings`, `satellite`, `monitors`, `signals` |
| Storage and cache | `altinfo/store.py` | SQLite: cache with expiry, history of every analysis and of each series |
| Errors | `altinfo/errors.py` | Typed errors with a message for the user |
| Settings and secrets | `altinfo/config.py`, `.env` | Keys are read by the backend only and never reach the browser |

What each search collects: every Kalshi series and every Polymarket market that mentions the asset by name or ticker
(plus related words for the covered names, such as Hormuz for Brent), filtered for relevance; when both venues price the
same question the market probability is their average weighted by traded volume, and both quotes are shown; news
coverage and tone over three months with the latest headlines from GDELT (free, no key).

How our probability is obtained, always stated on the page: the call of the event report where one exists (NVIDIA,
Brent); the company's own record of beats for earnings; for price contracts, what price and volatility imply, a neutral
yardstick that shows two markets disagreeing and not independent evidence.

**Dashboard** (`/dashboard`): the saved tickers ranked by gap, with their dates for the next three weeks and the alerts
of the last analysis. Save or remove tickers right there.

**Track record** (`/track`): the tickers you save, each with its latest reading and how the market and the gap moved since
you saved it. NVIDIA and Brent, the two calls of the event reports, are there from the start; their full reports and the
scoring of the calls open from that page. Save a ticker from the box on the page or with "Save to track record" on any
analysis. The dashboard and the track record share the same list, stored in `data/altinfo.db`.

If a source cannot be reached the analysis still runs on the last saved copy and says so under "Data status".
`ALTINFO_OFFLINE=1 python server/app.py` answers from the files in `data/raw` only. Tests: `python tests/test_app.py`.

### EIA key (optional, free)

Without a key the oil stocks are the figures printed in the report of 9 November. With one they update by themselves:
register at https://www.eia.gov/opendata/register.php, copy `.env.example` to `.env` and paste the key after
`EIA_API_KEY=`. The `.env` file is listed in `.gitignore`: never commit it.

## How the code maps to the product

| Product feature (product description) | Code |
|---|---|
| Event reports: earnings (NVIDIA) and commodities (Brent), four parts each | `notebooks/01_nvda_preview`, `notebooks/02_brent_preview`; `gap.py`, `satellite.py`, `earnings.py`, `valuation.py` |
| The gap score: evidence vs expectations | `gap.py` (Kalshi ladder, scenarios, Laplace base rate, verdict) |
| Valuation check: run-up, multiples vs peers and history, targets, futures curve | `valuation.py`, sections 8 (NVIDIA) and 7 (Brent) |
| Key drivers, risks and sources | last sections of notebooks 01 and 02 |
| Three commodity families: energy, metals, agriculture | `coverage.py` (10 names), weather from `sources/weather.py` |
| Dashboard: gap ranking, upcoming events, alerts feed, filters by sector, region and gap | `dashboard.py`, `notebooks/05_dashboard`, export `dashboard.html` |
| Signal pages: index history, odds, attention, link to the report | `signals.py`, export `signals/<NAME>.html` |
| Ticker search: satellite indices, supply chain map, expectations, attention, gap, linked assets | `search.py`, `coverage.py`, `notebooks/06_ticker_search` |
| Personalized monitors: sites, portfolios, disasters, who gains or loses | `monitors.py`, `sources/usgs.py`, `sources/firms.py`, `notebooks/07_monitors` |
| Free and Institutional tiers | `tiers.py`, free view in `notebooks/06_ticker_search`, table in `notebooks/05_dashboard` |
| Review of every call after the event | `scoring.py`, `notebooks/04_track_record` |
| Linked assets: how prices react to prediction markets | `eventbeta.py`, `notebooks/03_event_betas` |

## Structure

| Path | What it does |
|---|---|
| `altinfo/sources/` | Read only clients for Kalshi, Polymarket and Yahoo Finance (public endpoints, no keys) |
| `altinfo/gap.py` | Market probability from a Kalshi price ladder; our probability from weighted scenarios; the priced-in gap and its label |
| `altinfo/satellite.py` | Data Center Build-out Index (stage weights by GW), GW in fit-out, tank fill from shadows (fill = 1 − inner / outer shadow) |
| `altinfo/earnings.py` | Next day reaction after each report, drawdown from the record |
| `altinfo/scoring.py` | Brier score and track record against the market |
| `altinfo/eventbeta.py` | Event betas (returns on probability changes, Newey West errors), portfolio exposure, scenarios, hedge ratio |
| `altinfo/charts.py` | Charts in the preview style |
| `altinfo/coverage.py` | Covered companies and commodities: price ticker, linked assets, Kalshi series, Polymarket keywords, events, watched mines |
| `altinfo/dashboard.py` | Gap ranking, event calendar, alerts feed, HTML export |
| `altinfo/search.py` | Ticker search page |
| `altinfo/monitors.py` | Monitors: disasters near sites, activity drops, prediction market jumps, copper rule |
| `altinfo/sources/usgs.py` | USGS earthquake feed (free) |
| `altinfo/sources/firms.py` | NASA FIRMS active fires, last 7 days (free) |
| `altinfo/sources/weather.py` | Open-Meteo daily rain and temperature, anomaly against the 10 year normal (free) |
| `altinfo/valuation.py` | Run-up, multiples vs peers, trailing P/E history, consensus, futures curve spread |
| `altinfo/signals.py` | Signal histories per name, SVG charts, supply chain map, signal pages |
| `altinfo/tiers.py` | What the Free and Institutional tiers see |
| `notebooks/01_nvda_preview` | Stock data, last 8 reactions, build-out index and revenue nowcast, beat probability (90%) vs Polymarket (92%), attention, scenarios |
| `notebooks/02_brent_preview` | Price action, Hormuz flows, tank fills, Kalshi ladder (52%), scenario model (62%), gap +10 pts, robustness grid, Brent event betas |
| `notebooks/03_event_betas` | Event beta heatmap for 18 assets, out of sample test, portfolio scenarios |
| `notebooks/04_track_record` | Scores the two calls after 17 and 30 November |
| `notebooks/05_dashboard` | Gap ranking, calendar and alerts on live data; writes `dashboard.html` |
| `notebooks/06_ticker_search` | Search pages for NVDA, Brent and copper |
| `notebooks/07_monitors` | Copper monitor: live USGS check and replay of the Grasberg mud rush (Sept 2025) |
| `scripts/fetch_data.py` | Downloads prices, Fed decision markets, Brent/WTI/Hormuz/NVIDIA markets on Kalshi and Polymarket |
| `scripts/make_prototype_data.py` | Generates the illustrative satellite inputs in `data/prototype` |
| `scripts/build_notebooks.py` | Regenerates and executes the notebooks without a Jupyter kernel |

## Real and prototype data

Market, official and ship tracking figures are real and sourced in each preview. The satellite inputs in
`data/prototype` (campus construction stages, tank shadows), the mine activity series and output shares in the monitor,
the X topic shares and our own probabilities are
**illustrative prototype outputs**: the code shows how the platform turns such observations into indices and
calls, not the result of a real imagery analysis.

## Key formulas

* Priced-in gap = our probability − market probability; |gap| < 3 pts → PRICED IN.
* Brent: P(close > $96) = Σ weight × P(> $96 | scenario), uniform within each scenario's range
  → 0.30 × 0 + 0.50 × 0.83 + 0.20 × 1 = 62%, against 52% on Kalshi.
* NVIDIA beat: Laplace's rule on the last 8 reports, (8 + 1) / (8 + 2) = 90%, against 92% on Polymarket.
* Build-out index = Σ GW × stage weight / Σ GW, weights 15 / 40 / 60 / 85 / 100%.
* Event beta: r = α + β · Δp / 10 + ε, so β is the % return for a 10 point rise in the odds.

## The business proposal and this prototype

The business proposal describes the full product, built during the pilot and funded by the seed round. This
repository is the working prototype behind it. The engine, the gap, the track record and the interfaces are real
and run on live public data; the parts that need paid data, an imagery team or a long history of events are
simplified, and every input is labelled `real`, `reported` or `prototype` in the app and in the reports.

### Method: proposal against prototype

| Step in the proposal | In the full product | In this prototype |
|---|---|---|
| Evidence indices | Computer vision on imagery (cars, trucks, ships, campus stages, tank shadows), AIS ship tracking, seasonally adjusted z scores | The index maths runs on illustrative inputs (`satellite.py`: build-out index, tank fill from shadows); Hormuz flows and ships waiting as published; live free feeds for weather (rain against the 10 year normal), fires, earthquakes and EIA oil stocks against the 5 year average |
| Our probability, earnings | Logistic regression on the evidence indices, past surprises and revisions | Historical base rate with Laplace's rule: (beats + 1) / (reports + 2) over the last 8 reports (NVIDIA: 90%) |
| Our probability, commodities | Scenario model on observed flows and stocks | Same idea, implemented: three weighted scenarios give the probability of closing above each strike (Brent above $96: 62%) |
| Calibration | Platt scaling or isotonic regression on past events | Not yet: needs dozens of resolved events |
| Market probability | Liquidity filter, long shot bias adjustment, cross check with option implied probabilities | Liquidity and spread filter (`quality`); when Kalshi and Polymarket price the same question, their average weighted by traded volume. No long shot or options adjustment yet |
| Neutral yardstick | | Added in the prototype: what the price itself implies (random walk with 60 day volatility), compared with every ladder of price contracts |
| Attention | X and Stocktwits post volume, NLP pipeline (LDA, dynamic topics, TF IDF and word2vec sentiment, event dictionaries) | News attention from GDELT (coverage against its 3 month average, tone); when GDELT does not answer, Google News and Yahoo headlines with a word list tone. Topic shares on the signal pages are illustrative |
| The gap | Weighted up when evidence is strong and attention is low | Our probability minus the market's, labelled priced in under 3 points, plus a confidence score from 0 to 100 with its reasons |
| Event studies and backtest | Market model and Fama French abnormal returns regressed on the gap; walk forward backtest with costs, Sharpe and information ratios | Event betas instead: returns regressed on daily changes in prediction market probabilities, Newey West errors (`eventbeta.py`, notebook 03). The backtest needs a longer record of calls |
| Forecast evaluation | Brier score, log loss and calibration curves next to the market's | Brier score of every registered call, ours and the market's (`scoring.py`, Track record) |
| Kalshi word markets | Our probability from past earnings call transcripts | Contracts are recognised (`mention`) and shown, without a probability of our own |
| Learning from outcomes | Models refit after each event | Calls are scored after each event; nothing is refit yet |

### Product features: proposal against prototype

| Feature in the proposal | Why it is not live here | What the prototype does instead |
|---|---|---|
| Satellite imagery (campus stages, tank shadows, mine and crop activity) | Paid imagery licences (Planet, Maxar, Airbus) and an imagery team | Illustrative inputs in `data/prototype`; the code turns them into indices exactly as it would real readings |
| Ship tracking (AIS): tanker flows, ships waiting | Paid feeds (Kpler, Spire, MarineTraffic) | Figures as published in the Brent report |
| Attention on X and Stocktwits | X API access is paid; Stocktwits closed its API to new users | News attention from GDELT and headlines (see above) |
| Analyst consensus history, bank forecasts, cargo premiums | Licensed data (LSEG, FactSet, Bloomberg, Platts, Argus) | Yahoo Finance consensus and multiples; Murban as a proxy for Gulf premiums; EIA outlook |
| Prediction market data for resale | Kalshi and Polymarket data must be licensed (ICE, Tradeweb) to be redistributed | Read only use of the public APIs for research |
| Kalshi crop contracts | Listed in April 2026 and withdrawn by June 2026 | Futures prices; crop contracts are picked up automatically if relisted |
| User accounts, Free and Institutional tiers, email alerts | Needs logins, payments and hosting | One local user: saved tickers, stored analyses and in app alerts on the dashboard; tiers are a flag on the static ticker pages |
| Hosted, always on service | Needs hosting and scheduled jobs | Runs locally (`python server/app.py`); every search refreshes the data, with a cache |

## Legal note

The code only reads public market data. It does not place orders on any prediction market; Polymarket
trading is not available in the UK and parts of the EU. Not investment advice.
