"""CitySync 4 operations APIs: automatic evidence, persistent alerts, security audit."""
from flask import Blueprint, request, jsonify, send_from_directory
import auth, ops_intelligence, db
import v4_intelligence, v4_security, historical_baselines
from locations import BY_ID

bp=Blueprint('v4',__name__)

@bp.get('/operations')
def operations():
    return send_from_directory('static','operations.html')

@bp.get('/api/v4/overview')
def overview():
    report=v4_intelligence.evaluate_and_store()
    return jsonify({**report,'alerts':v4_security.alerts(),
                    'power_graph':v4_intelligence.power_graph(),
                    'historical_2025':historical_baselines.monthly_reference(),
                    'water_graph':v4_intelligence.water_graph(report),
                    'refresh_policy':{'browser_poll_seconds':20,'weather_cache_seconds':600,
                                      'traffic_collection_minutes':'See configured collector schedule'}})

@bp.get('/api/v4/predictions/traffic')
def traffic_pred():
    loc=request.args.get('location_id','')
    if loc not in BY_ID:return jsonify(error='Invalid location'),400
    return jsonify(ops_intelligence.trend(loc))

@bp.get('/api/v4/security')
@auth.admin_required
def security():
    return jsonify(v4_security.security_summary())

@bp.post('/api/v4/alerts/<path:key>/ack')
@auth.admin_required
def ack(key):
    if len(key)>150:return jsonify(error='Invalid alert identifier'),400
    if not v4_security.acknowledge(key):return jsonify(error='Alert is no longer active'),404
    return jsonify(ok=True)

@bp.get('/api/v4/alerts')
def get_alerts():
    return jsonify(alerts=v4_security.alerts())
