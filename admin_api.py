"""Admin-only API and browser login for CitySync.

All mutations require a signed admin session + CSRF, or an optional constant-time
API token for local scripts. Keys/passwords are never returned to the client.
"""
import logging
import math
import os
import tempfile
from datetime import datetime, date
from urllib.parse import urlsplit
from flask import Blueprint, jsonify, request, session

import auth
import config
import db
import data_collector
import water_service
from data_normalizer import now_ist, iso
from geo import in_box
from locations import BY_ID

bp = Blueprint('citysync_admin', __name__)
log = logging.getLogger(__name__)
MAX_KML_BYTES = 5 * 1024 * 1024


def fail(message, status=400):
    return jsonify(error=message), status


def audit(action, detail=''):
    with db.conn() as c:
        c.execute('INSERT INTO admin_audit(ts, action, detail, ip) VALUES(?,?,?,?)',
                  (iso(now_ist()), str(action)[:80], str(detail)[:300], str(request.remote_addr or '')[:64]))


def is_configured():
    return auth.problem() is None


@bp.get('/api/admin/me')
def who_am_i():
    configured = is_configured()
    logged = configured and session.get('admin') is True
    return jsonify(authenticated=bool(logged), configured=configured,
                   csrf=auth.csrf_token() if logged else None,
                   problem=None if configured else auth.problem(),
                   password_mode="HASH" if config.ADMIN_PASSWORD_HASH else ("PASSWORD" if config.ADMIN_PASSWORD else "NONE"))


@bp.post('/api/admin/login')
def login():
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or not isinstance(body.get('password'), str):
        return fail('Enter your admin password.', 400)
    pw = body['password']
    if len(pw) > 1024:
        return fail('Password is too long.', 400)
    ok, message = auth.attempt(str(request.remote_addr or ''), pw)
    if not ok:
        return fail(message, 429 if message.startswith('Too many failed attempts') else 401)
    session.clear()
    session['admin'] = True
    audit('login', 'Admin session opened')
    return jsonify(ok=True, csrf=auth.csrf_token())


@bp.post('/api/admin/logout')
def logout():
    session.clear()
    return jsonify(ok=True)


def _text(d, field, required=False, limit=300):
    v = d.get(field)
    if v is None:
        v = ''
    if not isinstance(v, str):
        raise ValueError(f'{field} must be text')
    v = v.strip()
    if required and not v:
        raise ValueError(f'{field} is required')
    if len(v) > limit:
        raise ValueError(f'{field} must be at most {limit} characters')
    return v or None


def _number(d, field, minimum=None, maximum=None):
    raw = d.get(field)
    if raw is None or raw == '':
        return None
    if isinstance(raw, bool):
        raise ValueError(f'{field} must be a number')
    try:
        value = float(raw)
    except (ValueError, TypeError):
        raise ValueError(f'{field} must be a number')
    if not math.isfinite(value) or (minimum is not None and value < minimum) or (maximum is not None and value > maximum):
        raise ValueError(f'{field} is outside the allowed range')
    return value


def _timestamp(d, field):
    value = _text(d, field, limit=45)
    if value is None:
        return None
    try:
        moment = datetime.fromisoformat(value)
        if moment.tzinfo is None or moment.utcoffset() is None:
            raise ValueError()
    except ValueError:
        raise ValueError(f'{field} must contain a full ISO datetime with timezone offset')
    return moment


def _notice(d):
    if not isinstance(d, dict):
        raise ValueError('Submit a JSON notice object')
    module = _text(d, 'module', required=True, limit=20)
    kind = _text(d, 'kind', required=True, limit=40)
    allowed = {'electricity': {'planned_outage'}, 'water': {'water_interruption', 'reservoir_level'}}
    if module not in allowed or kind not in allowed[module]:
        raise ValueError('Unsupported module/kind combination')
    area_text = _text(d, 'area_text', required=True, limit=200)
    source_name = _text(d, 'source_name', required=True, limit=200)
    source_url = _text(d, 'source_url', required=True, limit=1000)
    try:
        parsed = urlsplit(source_url)
        if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError()
    except ValueError:
        raise ValueError('source_url must be a valid http(s) URL without credentials')
    location_id = _text(d, 'location_id', limit=50)
    if location_id and location_id not in BY_ID:
        raise ValueError('Unknown monitoring location')
    lat = _number(d, 'lat', -90, 90)
    lon = _number(d, 'lon', -180, 180)
    radius = _number(d, 'radius_km', 0.01, 100)
    if any(x is not None for x in (lat, lon, radius)):
        if lat is None or lon is None or radius is None or not in_box(lat, lon):
            raise ValueError('lat/lon/radius_km must all be present and within Bengaluru area')
    start = _timestamp(d, 'start_time')
    end = _timestamp(d, 'end_time')
    value = _number(d, 'value', 0, 1_000_000)
    unit = _text(d, 'unit', limit=40)
    ndate = _text(d, 'notice_date', limit=12)
    if ndate:
        try: date.fromisoformat(ndate)
        except ValueError: raise ValueError('notice_date must be YYYY-MM-DD')
    if kind == 'reservoir_level':
        if value is None or not unit or not ndate:
            raise ValueError('Reservoir level needs value, unit and notice_date')
        if start is not None or end is not None:
            raise ValueError('Reservoir levels use notice_date rather than start/end times')
    else:
        if start is None or end is None or end <= start:
            raise ValueError('Outages/interruptions need a start and later end datetime')
        if value is not None or unit is not None:
            raise ValueError('Only reservoir levels accept value and unit')
    return {
        'module': module, 'kind': kind, 'title': _text(d, 'title', limit=120),
        'area_text': area_text, 'location_id': location_id,
        'lat': lat, 'lon': lon, 'radius_km': radius,
        'start_time': start.isoformat() if start else None,
        'end_time': end.isoformat() if end else None,
        'value': value, 'unit': unit,
        'source_name': source_name, 'source_url': source_url,
        'notice_date': ndate,
        'entered_at': iso(now_ist()),
    }


@bp.get('/api/admin/notices')
@auth.admin_required
def admin_notices():
    with db.conn() as c:
        rows = [dict(row) for row in c.execute('SELECT * FROM notices ORDER BY id DESC LIMIT 1000')]
    return jsonify(rows)


@bp.post('/api/notices')
@auth.admin_required
def create_notice():
    try:
        values = _notice(request.get_json(silent=True))
    except ValueError as e:
        return fail(str(e))
    keys = list(values)
    with db.conn() as c:
        cur = c.execute(f'INSERT INTO notices({",".join(keys)}) VALUES({",".join("?" for _ in keys)})',
                        [values[k] for k in keys])
        notice_id = cur.lastrowid
    audit('notice_created', f'{notice_id} {values["kind"]} {values["area_text"]}')
    return jsonify(id=notice_id, warning='Only a manually-entered notice; not live telemetry.'), 201


@bp.delete('/api/notices/<int:notice_id>')
@auth.admin_required
def remove_notice(notice_id):
    with db.conn() as c:
        deleted = c.execute('DELETE FROM notices WHERE id=?', (notice_id,)).rowcount
    if not deleted:
        return fail('Notice not found.', 404)
    audit('notice_deleted', str(notice_id))
    return jsonify(ok=True)


@bp.put('/api/admin/locations/<location_id>')
@auth.admin_required
def update_location(location_id):
    point = BY_ID.get(location_id)
    if point is None:
        return fail('Unknown monitoring location.', 404)
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return fail('Send a JSON object')
    try:
        lat = _number(body, 'lat', -90, 90)
        lon = _number(body, 'lon', -180, 180)
    except ValueError as e:
        return fail(str(e))
    if lat is None or lon is None or not in_box(lat, lon):
        return fail('Monitoring point must be inside the configured Bengaluru review area.')
    if body.get('clear_history', True) not in (True, False):
        return fail('clear_history must be true or false')
    old_lat, old_lon = point['lat'], point['lon']
    moved = (lat != old_lat or lon != old_lon)
    with db.conn() as c:
        c.execute('INSERT INTO location_overrides(location_id,lat,lon,updated_at) VALUES(?,?,?,?) '
                  'ON CONFLICT(location_id) DO UPDATE SET lat=excluded.lat,lon=excluded.lon,updated_at=excluded.updated_at',
                  (location_id, lat, lon, iso(now_ist())))
        if moved:
            c.execute('DELETE FROM matched_segments WHERE location_id=?', (location_id,))
        if moved and body.get('clear_history', True):
            c.execute('DELETE FROM readings WHERE module=? AND location_id=?', ('traffic', location_id))
    point.update(lat=lat, lon=lon)
    audit('point_updated', f'{location_id}: {old_lat},{old_lon} -> {lat},{lon}')
    return jsonify(ok=True, location=point, history_cleared=bool(moved and body.get('clear_history', True)),
                   note='Actual road suitability still needs manual verification. Collect fresh TomTom data.')


@bp.post('/api/admin/kml')
@auth.admin_required
def upload_kml():
    item = request.files.get('file')
    if item is None or not (item.filename or '').lower().endswith('.kml'):
        return fail('Choose a .kml file.')
    data = item.read(MAX_KML_BYTES + 1)
    if not data or len(data) > MAX_KML_BYTES:
        return fail('KML file must be 1 byte to 5 MB.')
    try:
        stations = water_service.parse_kml(data)
    except ValueError as e:
        return fail(f'Invalid KML: {e}')
    if len(stations) > 10000:
        return fail('KML has too many pumping stations.')
    inside = sum(bool(in_box(s['lat'], s['lon'])) for s in stations)
    folder = os.path.dirname(water_service.KML_PATH)
    os.makedirs(folder, exist_ok=True)
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(mode='wb', dir=folder, suffix='.tmp', delete=False) as out:
            tmp_path = out.name
            out.write(data)
        os.replace(tmp_path, water_service.KML_PATH)
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)
    water_service._cache.update(mtime=None, stations=[])
    audit('kml_uploaded', f'{len(stations)} pumping stations')
    return jsonify(ok=True, stations=len(stations), inside_bengaluru=inside)


@bp.get('/api/admin/system')
@auth.admin_required
def admin_system():
    with db.conn() as c:
        rows = c.execute('SELECT COUNT(*) FROM readings').fetchone()[0]
        audit_rows = [dict(r) for r in c.execute('SELECT * FROM admin_audit ORDER BY id DESC LIMIT 30')]
        jobs = [dict(r) for r in c.execute('SELECT * FROM collector_log ORDER BY id DESC LIMIT 20')]
        usage = [dict(r) for r in c.execute('SELECT * FROM api_usage ORDER BY period DESC, api')]
    return jsonify(tomtom_key_configured=bool(config.TOMTOM_API_KEY), stored_readings=rows,
                   api_usage=usage, jobs=jobs, audit=audit_rows,
                   pumping_stations=len(water_service.pumping_stations()),
                   intervals_min={'flow': config.FLOW_INTERVAL_MIN, 'incidents': config.INCIDENT_INTERVAL_MIN},
                   budgets={'flow': config.FLOW_MONTHLY_BUDGET, 'incidents': config.INCIDENT_MONTHLY_BUDGET})


@bp.post('/api/collect')
@auth.admin_required
def collect_now():
    try:
        data_collector.run_flow()
        data_collector.run_incidents()
        with db.conn() as c:
            logs = [dict(r) for r in c.execute('SELECT * FROM collector_log ORDER BY id DESC LIMIT 2')]
        audit('manual_collect', 'TomTom flow and incident collection started')
        return jsonify(ok=bool(logs) and all(l['ok'] for l in logs), recent_jobs=logs)
    except Exception as e:
        log.exception('Manual collector failed')
        return fail('Collector failed; check server logs and TomTom configuration.', 503)
