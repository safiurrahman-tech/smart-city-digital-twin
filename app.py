import json, logging, os, secrets
from flask import Flask, jsonify, request, send_from_directory, abort
import config, db, traffic_service, electricity_service, water_service, impact_engine, data_collector, decision_lab, ops_intelligence, cascade_engine
from data_normalizer import now_ist, iso, freshness
from locations import LOCATIONS, BY_ID, load_overrides
from sources import SOURCES

logging.basicConfig(level=logging.INFO)
app = Flask(__name__, static_folder="static", static_url_path="")
db.init()
load_overrides()
app.secret_key = config.SECRET_KEY or secrets.token_urlsafe(32)
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Strict",
                  SESSION_COOKIE_SECURE=config.COOKIE_SECURE, MAX_CONTENT_LENGTH=6*1024*1024)
import admin_api, twin_api, v4_api, v4_security
v4_security.init()
app.register_blueprint(v4_api.bp)
app.register_blueprint(admin_api.bp)
twin_api.init()
app.register_blueprint(twin_api.bp)

@app.after_request
def security_headers(resp):
    """Defence-in-depth browser protections for every response."""
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    resp.headers.setdefault("Permissions-Policy", "geolocation=(), camera=(), microphone=()")
    resp.headers.setdefault("Content-Security-Policy",
        "default-src 'self'; script-src 'self' https://unpkg.com https://cdnjs.cloudflare.com; "
        "style-src 'self' 'unsafe-inline' https://unpkg.com https://cdnjs.cloudflare.com https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; img-src 'self' data: https:; connect-src 'self'; "
        "frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
    if request.path.startswith("/api/"):
        resp.headers.setdefault("Cache-Control", "no-store")
    return resp

@app.after_request
def v4_security_monitor(response):
    # Server-side denial of protected API actions is logged without credentials.
    if response.status_code in (401,403,429) and (request.path.startswith('/api/v4/alerts/') or
        (request.path.startswith('/api/admin/') and request.path not in ('/api/admin/me','/api/admin/login')) or
        request.path == '/api/v4/security'):
        try:
            request.environ['v4_denial_status']=response.status_code
            v4_security.log_denial()
        except Exception:
            app.logger.exception('Could not record access denial')
    return response

@app.get("/admin")
def admin_page():
    return send_from_directory("static", "admin.html")

def _latest_traffic_rows():
    with db.conn() as c:
        rows = c.execute("""SELECT r.* FROM readings r JOIN
          (SELECT location_id, metric, MAX(collected_at) m FROM readings WHERE module='traffic' GROUP BY 1,2) x
          ON r.location_id=x.location_id AND r.metric=x.metric AND r.collected_at=x.m
          WHERE r.module='traffic'""").fetchall()
    # Avoid mixing previously sampled nearby roads after locations.py coordinates change.
    return [dict(r) for r in rows if r["location_id"] in BY_ID and
            r["lat"] == BY_ID[r["location_id"]]["lat"] and
            r["lon"] == BY_ID[r["location_id"]]["lon"]]

@app.get("/")
def index():
    return send_from_directory("static", "command.html")

@app.get("/legacy")
def legacy():
    return send_from_directory("static", "index.html")

@app.get("/api/health")
def health():
    with db.conn() as c:
        logs = [dict(r) for r in c.execute("SELECT * FROM collector_log ORDER BY id DESC LIMIT 10")]
        usage = [dict(r) for r in c.execute("SELECT * FROM api_usage")]
    return jsonify(now=iso(now_ist()), tomtom_key_configured=bool(config.TOMTOM_API_KEY),
                   recent_jobs=logs, api_usage=usage)

@app.get("/api/locations")
def locations():
    return jsonify(LOCATIONS)

@app.get("/api/sources")
def sources():
    return jsonify(SOURCES)

@app.get("/api/traffic")
def traffic():
    by = {l["id"]: {**l, "metrics": {}, "status": "UNAVAILABLE", "reason": None} for l in LOCATIONS}
    for r in _latest_traffic_rows():
        st, age = freshness(r["status"], r["collected_at"], config.FLOW_INTERVAL_MIN)
        r["status"], r["age_seconds"] = st, age
        loc = by.get(r["location_id"])
        if loc:
            loc["metrics"][r["metric"]] = r
            loc["status"] = st
    for l in by.values():
        if not l["metrics"]:
            l["reason"] = ("TOMTOM_API_KEY not set" if not config.TOMTOM_API_KEY
                           else "No successful collection yet")
    return jsonify(locations=list(by.values()), generated_at=iso(now_ist()))

@app.get("/api/traffic/segments")
def traffic_segments():
    """Latest TomTom-matched road geometry. Not proof of road-name correctness."""
    with db.conn() as c:
        saved = [dict(r) for r in c.execute("SELECT * FROM matched_segments")]
    by = {r["location_id"]: r for r in saved}
    result = []
    for loc in LOCATIONS:
        row = by.get(loc["id"])
        matched = bool(row and row["lat"] == loc["lat"] and row["lon"] == loc["lon"])
        status, age = freshness("LIVE", row["collected_at"], config.FLOW_INTERVAL_MIN) if matched else ("UNAVAILABLE", None)
        result.append({"location_id":loc["id"],"name":loc["name"],"point":{"lat":loc["lat"],"lon":loc["lon"]},
                       "status":status, "age_seconds":age, "frc":row["frc"] if matched else None,
                       "coordinates":json.loads(row["coordinates_json"]) if matched else [],
                       "collected_at":row["collected_at"] if matched else None,
                       "verified_main_road":False})
    return jsonify(segments=result, note="Matched road geometry is from TomTom. Road names and main-road suitability require human map verification.")

@app.get("/api/traffic/incidents")
def incidents():
    with db.conn() as c:
        rows = [dict(r) for r in c.execute("SELECT * FROM incidents")]
    status = "UNAVAILABLE"
    if rows:
        status, _ = freshness("LIVE", rows[0]["collected_at"], config.INCIDENT_INTERVAL_MIN)
    return jsonify(status=status, source="TomTom Traffic Incidents", incidents=rows,
                   total_records=len(rows), scope="Configured city-wide bounding box; not limited to seven monitoring points",
                   note=None if rows else "No incident snapshot (none reported in the box, or not collected yet).")

@app.get("/api/traffic/history")
def history():
    loc = request.args.get("location_id", "")
    if loc not in BY_ID:
        abort(404)
    with db.conn() as c:
        params = (loc, BY_ID[loc]["lat"], BY_ID[loc]["lon"])
        rows = [dict(r) for r in c.execute(
            "SELECT collected_at, metric, value FROM readings WHERE module='traffic' AND location_id=? "
            "AND lat=? AND lon=? AND metric IN ('current_speed','free_flow_speed') "
            "ORDER BY collected_at DESC LIMIT 400", params)]
        stats = c.execute(
            "SELECT COUNT(DISTINCT collected_at) AS snapshots, MIN(collected_at) AS oldest, "
            "MAX(collected_at) AS newest FROM readings WHERE module='traffic' AND location_id=? "
            "AND lat=? AND lon=? AND metric='current_speed'", params).fetchone()
    samples = int(stats["snapshots"] or 0)
    return jsonify(location_id=loc, rows=list(reversed(rows)),
                   snapshot_count=samples, oldest=stats["oldest"], newest=stats["newest"],
                   label="Collected by this app for the current configured point (not an official or historical archive)")

@app.post("/api/decision-lab/simulate")
def decision_lab_simulate():
    """Runs ONLY a local hypothetical scenario over existing TomTom readings.

    This endpoint never fetches TomTom data and never stores scenarios server-side.
    """
    payload = request.get_json(silent=True)
    try:
        return jsonify(decision_lab.simulate(payload))
    except decision_lab.ValidationError as exc:
        return jsonify(error=str(exc)), 400
    except decision_lab.NoTrafficData as exc:
        return jsonify(error=str(exc)), 409


@app.get("/api/ops/summary")
def ops_summary():
    return jsonify(ops_intelligence.summary())

@app.get("/api/ops/trend")
def ops_trend():
    location_id = request.args.get("location_id", "")
    try:
        return jsonify(ops_intelligence.trend(location_id))
    except KeyError:
        return jsonify(error="Unknown monitoring location"), 404

@app.post("/api/ops/demo-simulate")
def demo_simulate():
    """Offline reproducible hypothetical scenario; never identified as measured traffic."""
    payload = request.get_json(silent=True)
    try:
        return jsonify(decision_lab.simulate_demo(payload))
    except decision_lab.ValidationError as exc:
        return jsonify(error=str(exc)), 400

@app.post("/api/ops/cascade-simulate")
def cascade_simulate():
    """Illustrative water-pump dependency, NOT a real BWSSB pump or pressure signal."""
    try:
        return jsonify(cascade_engine.simulate(request.get_json(silent=True)))
    except cascade_engine.CascadeValidationError as exc:
        return jsonify(error=str(exc)), 400

@app.get("/api/electricity")
def electricity():
    return jsonify(electricity_service.summary())

@app.get("/api/water")
def water():
    return jsonify(water_service.summary())

@app.get("/api/impact")
def impact():
    return jsonify(impact_engine.evaluate())

if __name__ == "__main__":
    if os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        data_collector.start()
    app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False)
