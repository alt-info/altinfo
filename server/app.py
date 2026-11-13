"""ALT/INFO backend: a thin HTTP layer over altinfo.engine. No analysis logic lives here.

    python server/app.py            then open http://127.0.0.1:8000

Routes
  GET  /                    the single page interface
  POST /api/analyze         {"q": "NVDA"} -> {"job": id}; the analysis runs in the background
  GET  /api/jobs/<id>       progress (stage by stage), then the result or a typed error
  GET  /api/assets          names covered in depth, for the suggestions under the search box
  GET  /api/history/<key>   stored series and past analyses of one asset
  GET  /api/watchlist       the saved tickers of the track record, each with its stored analyses
  POST /api/watchlist       {"q": "AAPL"} saves a ticker; DELETE /api/watchlist/<key> removes it
  GET  /api/dashboard       the saved tickers ranked by gap, with their next events and alerts
  GET  /api/news?q=...      news attention for a query, loaded in the background (GDELT is slow and rate limited)
  GET  /api/calls           the calls of the event reports, scored once the event is over
  GET  /api/health          is the server up, which optional sources are on
  GET  /files/...           the static reports and dashboard built by scripts/build_notebooks.py

Secrets stay in altinfo.config (environment or .env). The browser only ever talks to these routes.
"""
import os
import sys
import threading
import time
import uuid
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_from_directory

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from altinfo import config, engine, store  # noqa: E402
from altinfo.sources import http as _http  # noqa: E402
from altinfo.brand import FAVICON, logo_svg  # noqa: E402
from altinfo.coverage import COVERAGE  # noqa: E402
from altinfo.errors import AltInfoError, InvalidQuery  # noqa: E402

WEB = ROOT / "web"
OFFLINE = os.environ.get("ALTINFO_OFFLINE", "") == "1"   # answer from saved files only (no network)
MAX_RUNNING = 4
JOB_LIMIT = 240          # seconds: after this the page is told the analysis took too long
# interactive settings: short timeouts and few retries, so a blocked site costs seconds, not minutes
_http.TIMEOUT, _http.RETRY_PAUSE, _http.MAX_TRIES = 12, 0.6, 2
app = Flask(__name__, static_folder=str(WEB), static_url_path="/static")
JOBS, LOCK = {}, threading.Lock()


def _run(job_id, q):
    def progress(i, label):
        with LOCK:
            if JOBS[job_id]["state"] == "running":
                JOBS[job_id].update(stage=i, label=label)
    try:
        result = engine.analyze(q, progress=progress, offline=OFFLINE)
        with LOCK:
            JOBS[job_id].update(state="done", stage=len(engine.STAGES) - 1, label=engine.STAGES[-1], result=result)
    except AltInfoError as e:
        with LOCK:
            JOBS[job_id].update(state="error", error=e.to_dict())
    except Exception as e:  # never leak a traceback to the browser
        app.logger.exception("analysis failed for %r", q)
        with LOCK:
            JOBS[job_id].update(state="error", error={"code": "internal", "message": "Something went wrong while analysing this asset.",
                                                       "detail": type(e).__name__})


def _sweep():
    now = time.time()
    for k in [k for k, j in JOBS.items() if now - j["created"] > 900]:
        JOBS.pop(k, None)


@app.after_request
def _headers(r):
    r.headers["X-Content-Type-Options"] = "nosniff"
    r.headers["Referrer-Policy"] = "no-referrer"
    if not request.path.startswith("/files/"):   # the app itself runs no inline script or style
        r.headers["Content-Security-Policy"] = ("default-src 'self'; style-src 'self' https://fonts.googleapis.com; "
                                                "font-src https://fonts.gstatic.com; img-src 'self' data:; script-src 'self'")
    if request.path.startswith("/api/"):
        r.headers["Cache-Control"] = "no-store"
    return r


@app.get("/")
@app.get("/track")
@app.get("/dashboard")
def index():
    html = (WEB / "index.html").read_text()
    html = html.replace("{{LOGO}}", logo_svg(24, letters="#ffffff")).replace("{{LOGO_DARK}}", logo_svg(44)).replace("{{FAVICON}}", FAVICON)
    return Response(html, mimetype="text/html")


@app.post("/api/analyze")
def analyze():
    q = ((request.get_json(silent=True) or {}).get("q") or "").strip()
    if not q or len(q) > 40:
        e = InvalidQuery("Type a ticker such as NVDA or a commodity such as copper.")
        return jsonify(error=e.to_dict()), e.status
    with LOCK:
        _sweep()
        if sum(j["state"] == "running" for j in JOBS.values()) >= MAX_RUNNING:
            return jsonify(error={"code": "busy", "message": "Several analyses are running. Try again in a few seconds."}), 429
        job_id = uuid.uuid4().hex[:16]
        JOBS[job_id] = {"state": "running", "stage": 0, "label": engine.STAGES[0], "created": time.time(), "q": q}
    threading.Thread(target=_run, args=(job_id, q), daemon=True).start()
    return jsonify(job=job_id, stages=engine.STAGES)


@app.get("/api/jobs/<job_id>")
def job(job_id):
    with LOCK:
        j = dict(JOBS.get(job_id) or {})
    if not j:
        return jsonify(error={"code": "unknown_job", "message": "This analysis expired. Run it again."}), 404
    if j["state"] == "running" and time.time() - j["created"] > JOB_LIMIT:
        with LOCK:
            JOBS[job_id].update(state="error", error={"code": "timeout", "message": "This analysis is taking too long.",
                                                      "detail": "A data source is very slow. Try again in a minute: the data already downloaded is kept."})
            j = dict(JOBS[job_id])
    return jsonify({k: j.get(k) for k in ("state", "stage", "label", "result", "error")} |
                   {"stages": engine.STAGES, "elapsed": round(time.time() - j["created"])})


@app.get("/api/assets")
def assets():
    return jsonify([{"key": k, "name": v["name"], "kind": v["kind"], "group": v["group"]} for k, v in COVERAGE.items()])


@app.get("/api/history/<key>")
def history(key):
    key = key.upper()[:20]
    return jsonify(asset=key, market_prob=store.get_series(key, "market_prob"), price=store.get_series(key, "price"),
                   analyses=store.past_analyses(key))


@app.get("/files/<path:name>")
def files(name):
    """The static reports, dashboard and signal pages built by scripts/build_notebooks.py (html only)."""
    ok = name.endswith(".html") and (name == "dashboard.html" or name.startswith(("notebooks/", "signals/")))
    if not ok:
        return jsonify(error={"code": "not_found", "message": "Not found."}), 404
    return send_from_directory(str(ROOT), name)


@app.get("/api/watchlist")
def watchlist():
    out = []
    for w in store.watch_list():
        past = store.past_analyses(w["key"], limit=60)
        out.append(w | {"analyses": past, "last": past[-1] if past else None,
                        "first_after_save": next((p for p in past if p["at"] >= w["added_at"] - 1), None)})
    return jsonify(out)


@app.post("/api/watchlist")
def watch_add():
    from altinfo.fetch import Fetcher
    from altinfo.resolver import resolve
    q = ((request.get_json(silent=True) or {}).get("q") or "").strip()
    try:
        a = resolve(q, Fetcher(offline=OFFLINE))
    except AltInfoError as e:
        return jsonify(error=e.to_dict()), e.status
    store.watch_add(a["key"], a["name"], q)
    return jsonify(ok=True, key=a["key"], name=a["name"])


@app.get("/api/dashboard")
def dashboard():
    """Where is the gap largest among the saved tickers? Built from the latest stored analysis of each one."""
    import pandas as pd
    rows, events, alerts = [], [], []
    today = pd.Timestamp.now().normalize()
    for w in store.watch_list():
        at, d = store.latest_analysis(w["key"])
        if d is None:
            rows.append({"key": w["key"], "name": w["name"], "analysed": False})
            continue
        h, a, p = d.get("headline") or {}, d.get("asset") or {}, d.get("price") or {}
        past = store.past_analyses(w["key"], limit=2)
        prev = past[0] if len(past) == 2 else None
        rows.append({"key": w["key"], "name": a.get("name", w["name"]), "group": a.get("group"), "kind": a.get("kind"),
                     "analysed": True, "at": at, "question": h.get("question"), "ours": h.get("ours"), "market": h.get("market"),
                     "gap_pts": h.get("gap_pts"), "label": h.get("label"), "closes": h.get("closes"),
                     "confidence": (d.get("confidence") or {}).get("score"), "level": (d.get("confidence") or {}).get("level"),
                     "price": p.get("last"), "change_1w": p.get("change_1w"), "change_1m": p.get("change_1m"),
                     "spark": [x["v"] for x in (p.get("series") or [])[-60:]], "next_event": d.get("next_event")})
        from altinfo.coverage import COVERAGE
        for dt, e in (COVERAGE.get(w["key"], {}).get("events") or []):
            if today <= pd.Timestamp(dt) <= today + pd.Timedelta(days=21):
                events.append({"date": dt, "event": e, "key": w["key"], "name": a.get("name", w["name"])})
        if h.get("closes") and pd.Timestamp(h["closes"]) >= today:
            events.append({"date": h["closes"], "event": "Our call settles: " + h.get("question", ""), "key": w["key"],
                           "name": a.get("name", w["name"]), "gap_pts": h.get("gap_pts"), "call": True})
        for x in (d.get("evidence") or {}).get("alerts") or []:
            alerts.append({"type": "Site", "key": w["key"], "name": a.get("name"), "text": f"{x['site']}: {x['alert']}", "at": at})
        if p.get("change_1w") is not None and abs(p["change_1w"]) >= 0.05:
            alerts.append({"type": "Price", "key": w["key"], "name": a.get("name"), "text": f"price {p['change_1w']:+.1%} in a week", "at": at})
        if h.get("gap_pts") is not None and abs(h["gap_pts"]) >= 5:
            alerts.append({"type": "Gap", "key": w["key"], "name": a.get("name"), "text": f"gap {h['gap_pts']:+.0f} pts, {h['label'].lower()}", "at": at})
        if prev and prev.get("market") is not None and h.get("market") is not None and abs(h["market"] - prev["market"]) >= 0.10:
            alerts.append({"type": "Market", "key": w["key"], "name": a.get("name"),
                           "text": f"market {100 * (h['market'] - prev['market']):+.0f} pts since the previous analysis", "at": at})
    rows.sort(key=lambda r: (not r.get("analysed"), r.get("gap_pts") is None, -abs(r.get("gap_pts") or 0)))
    events.sort(key=lambda e: e["date"])
    alerts.sort(key=lambda x: -(x["at"] or 0))
    return jsonify(rows=rows, events=events, alerts=alerts)


@app.delete("/api/watchlist/<key>")
def watch_remove(key):
    store.watch_remove(key.upper()[:20])
    return jsonify(ok=True)


NEWS = {}   # query -> {"state": "loading" | "done", "result": ..., "at": time}


def _news(q, t):
    try:
        r = engine.news_for(q, t, offline=OFFLINE)
    except Exception as e:  # never leak a traceback to the browser
        app.logger.exception("news failed for %r", q)
        r = {"available": False, "summary": "News coverage could not be loaded right now.", "note": type(e).__name__}
    with LOCK:
        NEWS[q] = {"state": "done", "result": r, "at": time.time()}


@app.get("/api/news")
def news():
    q = (request.args.get("q") or "").strip()[:120]
    t = (request.args.get("t") or "").strip().upper()[:20] or None
    if not q:
        return jsonify(error={"code": "invalid_query", "message": "No query."}), 400
    with LOCK:
        j = NEWS.get(q)
        stale = j and j["state"] == "done" and (not j["result"].get("available")) and time.time() - j["at"] > 60
        if j is None or stale:     # start (or restart a failed one after a minute) in the background
            NEWS[q] = {"state": "loading", "at": time.time()}
            threading.Thread(target=_news, args=(q, t), daemon=True).start()
            return jsonify(state="loading")
    return jsonify(state=j["state"], result=j.get("result"))


@app.get("/api/calls")
def calls():
    """The probabilities registered in the event reports of 9 Nov 2026, scored with the Brier score once resolved."""
    import json
    import pandas as pd
    from altinfo import scoring
    c = pd.DataFrame(json.load(open(config.SNAPSHOT))["calls"])
    c["outcome"] = c["outcome"].astype(float)
    scored, summary = scoring.track_record(c)
    reports = {"NVDA": "/files/notebooks/01_nvda_preview.html", "Brent": "/files/notebooks/02_brent_preview.html"}
    rows = []
    for r in scored.to_dict("records"):
        rep = next((u for k, u in reports.items() if r["event"].startswith(k)), None)
        rows.append({k: (None if isinstance(v, float) and v != v else v) for k, v in r.items()} | {"report": rep})
    clean = {k: (None if isinstance(v, float) and v != v else v) for k, v in summary.items()}
    return jsonify(calls=rows, summary=clean, made_on="9 Nov 2026", scoring="/files/notebooks/04_track_record.html")


@app.get("/api/health")
def health():
    return jsonify(ok=True, offline=OFFLINE, config=config.public_config())


if __name__ == "__main__":
    print(f"ALT/INFO running on http://{config.HOST}:{config.PORT}  (Ctrl+C to stop)" + ("  [offline mode]" if OFFLINE else ""))
    if not config.EIA_API_KEY:
        print("  EIA_API_KEY not set: oil stocks use the figures of the 9 Nov report. See README, 'EIA key'.")
    app.run(host=config.HOST, port=config.PORT, threaded=True, debug=False)
