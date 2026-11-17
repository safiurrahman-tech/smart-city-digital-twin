"""TomTom Traffic Flow + Incidents. Key stays server-side. Handles: missing key, 429, timeouts,
budget exhaustion, empty payloads. Endpoint paths follow TomTom's public docs at time of writing;
run scripts/test_connections.py to confirm them with YOUR key before relying on them."""
import json, logging, time
from math import isfinite
import requests
import config, db
from data_normalizer import now_ist, iso, normalize_flow, normalize_incidents

log = logging.getLogger("traffic")
FLOW_URL = "https://api.tomtom.com/traffic/services/4/flowSegmentData/absolute/10/json"
INCIDENT_URL = "https://api.tomtom.com/traffic/services/5/incidentDetails"
INCIDENT_FIELDS = ("{incidents{type,geometry{type,coordinates},properties{id,iconCategory,"
                   "magnitudeOfDelay,events{description,code},startTime,endTime,from,to,length,delay,roadNumbers}}}")

class SourceError(Exception):
    pass

def _budget_ok(api, limit):
    period = now_ist().strftime("%Y-%m")
    with db.conn() as c:
        r = c.execute("SELECT count FROM api_usage WHERE api=? AND period=?", (api, period)).fetchone()
    return (r["count"] if r else 0) < limit

def _count(api):
    period = now_ist().strftime("%Y-%m")
    with db.conn() as c:
        c.execute("INSERT INTO api_usage(api,period,count) VALUES(?,?,1) "
                  "ON CONFLICT(api,period) DO UPDATE SET count=count+1", (api, period))

def _get(url, params, retries=2):
    if not config.TOMTOM_API_KEY:
        raise SourceError("TOMTOM_API_KEY not set")
    params = {**params, "key": config.TOMTOM_API_KEY}
    for attempt in range(retries + 1):
        try:
            r = requests.get(url, params=params, timeout=10)
        except requests.RequestException as e:
            if attempt == retries:
                raise SourceError(f"network error: {type(e).__name__}")
            time.sleep(2 ** attempt); continue
        if r.status_code == 429:
            wait = int(r.headers.get("Retry-After", 2 ** (attempt + 1)))
            if attempt == retries:
                raise SourceError("rate limited (429)")
            time.sleep(min(wait, 30)); continue
        if r.status_code in (401, 403):
            raise SourceError(f"auth rejected ({r.status_code}); check key / product access")
        if r.status_code >= 500:
            if attempt == retries:
                raise SourceError(f"upstream error {r.status_code}")
            time.sleep(2 ** attempt); continue
        if r.status_code != 200:
            raise SourceError(f"unexpected status {r.status_code}")
        try:
            return r.json()
        except ValueError:
            raise SourceError("non-JSON response")

def fetch_flow(location):
    if not _budget_ok("tomtom_flow", config.FLOW_MONTHLY_BUDGET):
        raise SourceError("monthly flow budget reached")
    _count("tomtom_flow")
    return _get(FLOW_URL, {"point": f"{location['lat']},{location['lon']}", "unit": "KMPH"})

def fetch_incidents(bbox=config.CITY_BBOX):
    if not _budget_ok("tomtom_incidents", config.INCIDENT_MONTHLY_BUDGET):
        raise SourceError("monthly incident budget reached")
    _count("tomtom_incidents")
    return _get(INCIDENT_URL, {"bbox": ",".join(map(str, bbox)), "fields": INCIDENT_FIELDS,
                               "language": "en-GB", "timeValidityFilter": "present"})

def _segment_geometry(payload):
    """Validate and retain TomTom's returned road polyline, never guessed coordinates."""
    flow = (payload or {}).get("flowSegmentData") or {}
    raw = ((flow.get("coordinates") or {}).get("coordinate") or [])
    points = []
    for point in raw[:2000]:
        if not isinstance(point, dict):
            continue
        lat, lon = point.get("latitude"), point.get("longitude")
        if (isinstance(lat, (int, float)) and not isinstance(lat, bool)
                and isinstance(lon, (int, float)) and not isinstance(lon, bool)
                and isfinite(lat) and isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
            points.append([float(lat), float(lon)])
    return points, str(flow.get("frc") or "unknown")


def save_matched_segment(location, payload, collected_at):
    """One latest matched polyline per monitoring point; no API calls."""
    coords, frc = _segment_geometry(payload)
    if len(coords) < 2:
        return False
    with db.conn() as c:
        c.execute("""INSERT INTO matched_segments(location_id,lat,lon,frc,coordinates_json,collected_at)
            VALUES(?,?,?,?,?,?) ON CONFLICT(location_id) DO UPDATE SET
            lat=excluded.lat,lon=excluded.lon,frc=excluded.frc,
            coordinates_json=excluded.coordinates_json,collected_at=excluded.collected_at""",
            (location["id"], location["lat"], location["lon"], frc, json.dumps(coords), iso(collected_at)))
    return True

def save_readings(rows):
    with db.conn() as c:
        for r in rows:
            r.setdefault("value_text", None); r.setdefault("value", None)
            c.execute("""INSERT INTO readings(module,metric,location_id,lat,lon,value,value_text,unit,source,
              source_url,observed_at,collected_at,status,completeness,coverage) VALUES
              (:module,:metric,:location_id,:lat,:lon,:value,:value_text,:unit,:source,:source_url,
               :observed_at,:collected_at,:status,:completeness,:coverage)""",
                      {"lat": None, "lon": None, "coverage": None, **r})

def save_incidents(rows):
    with db.conn() as c:
        c.execute("DELETE FROM incidents")  # incidents are a snapshot, not a history
        for r in rows:
            c.execute("""INSERT INTO incidents(source_id,lat,lon,category,magnitude,description,road,from_text,
              to_text,delay_s,length_m,start_time,end_time,collected_at) VALUES
              (:source_id,:lat,:lon,:category,:magnitude,:description,:road,:from_text,:to_text,:delay_s,
               :length_m,:start_time,:end_time,:collected_at)""", r)

def collect_flow(locations):
    results = {}
    for loc in locations:
        try:
            payload = fetch_flow(loc)
            stamp = now_ist()
            rows = normalize_flow(loc, payload, stamp)
            if not rows:
                raise SourceError("empty payload")
            save_readings(rows)
            save_matched_segment(loc, payload, stamp)
            results[loc["id"]] = "ok"
        except SourceError as e:
            log.warning("flow %s: %s", loc["id"], e)
            results[loc["id"]] = str(e)
            if "budget" in str(e) or "auth" in str(e) or "KEY" in str(e):
                break  # no point hammering the API
    return results

def collect_incidents():
    try:
        rows = normalize_incidents(fetch_incidents(), now_ist())
        save_incidents(rows)
        return f"ok ({len(rows)} incidents)"
    except SourceError as e:
        log.warning("incidents: %s", e)
        return str(e)
