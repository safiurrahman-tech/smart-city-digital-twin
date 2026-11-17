"""REST API for evidence-aware CitySync digital twin."""
import csv
import io
import json
from datetime import date
from flask import Blueprint, jsonify, request, Response
import db, ops_intelligence, twin_engine, weather_service, advanced_intelligence, economic_profile
from locations import LOCATIONS, BY_ID
from data_normalizer import iso,now_ist

bp=Blueprint('twin',__name__)

def init():
    with db.conn() as c:
        c.executescript('''CREATE TABLE IF NOT EXISTS twin_scenarios (
          id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL,
          preset TEXT NOT NULL, location_id TEXT NOT NULL,
          actions TEXT NOT NULL, inputs_json TEXT NOT NULL,
          result_json TEXT NOT NULL, health_before REAL, health_after REAL,
          baseline_source TEXT NOT NULL);
          CREATE INDEX IF NOT EXISTS twin_scenarios_ix ON twin_scenarios(created_at,location_id);
        ''')

@bp.get('/api/twin/catalog')
def catalog():
    return jsonify(presets=twin_engine.PRESETS,actions=twin_engine.ACTIONS,
                   fields={**twin_engine.SPECS,**twin_engine.ECON_SPECS},economic_defaults=twin_engine.ECON_DEFAULTS,locations=LOCATIONS,
                   note='Controls are hypothetical; TomTom nearest-road-segment baseline may be live when available.')

@bp.get('/api/twin/model')
def model():
    return jsonify(twin_engine.model_card())

@bp.get('/api/weather')
def weather():
    return jsonify(weather_service.current_weather())

@bp.get('/api/twin/overview')
def overview():
    data=ops_intelligence.summary()
    with db.conn() as c:
        stored=c.execute('SELECT COUNT(*) n FROM twin_scenarios').fetchone()['n']
    # Utility metrics intentionally not synthesized as observed telemetry.
    return jsonify(generated_at=data['generated_at'],metrics=data['metrics'],
                   alerts=data['alerts'], locations=data['locations'],
                   readiness=data['readiness'],scenario_count=stored,
                   utility_telemetry='UNAVAILABLE',
                   demo_city_health='SIMULATED_ONLY',
                   note='Observed speed ratios from TomTom. Utility percentages and city-health scores appear only inside explicitly simulated scenarios.')

@bp.get('/api/twin/economic-profile')
def economic_profile_api():
    try:
        return jsonify(economic_profile.derive(request.args.get('location_id',''),request.args.get('hour')))
    except KeyError:
        return jsonify(error='Unknown monitoring location'),400
    except ValueError as exc:
        return jsonify(error=str(exc)),400

@bp.post('/api/twin/execute')
def execute():
    payload=request.get_json(silent=True)
    profile=None
    if isinstance(payload,dict) and payload.get('economics_mode')=='auto':
        try:
            profile=economic_profile.derive(payload.get('location_id'),payload.get('hour'))
        except (KeyError,TypeError):
            return jsonify(error='Unknown monitoring location'),400
        except ValueError as exc:
            return jsonify(error=str(exc)),400
        payload={**{k:v for k,v in payload.items() if k not in twin_engine.ECON_SPECS},**profile['values']}
    try:
        observations={x['id']:x for x in ops_intelligence._snapshots()}
        outcome=twin_engine.simulate(payload, LOCATIONS, observations)
        if profile: outcome['economic_profile']=profile
    except (ValueError,TypeError) as exc:
        return jsonify(error=str(exc)),400
    save=payload.get('save',True)
    if not isinstance(save,bool):
        return jsonify(error='save must be true or false'),400
    if save:
        with db.conn() as c:
            cursor=c.execute('INSERT INTO twin_scenarios (created_at,preset,location_id,actions,inputs_json,result_json,health_before,health_after,baseline_source) VALUES (?,?,?,?,?,?,?,?,?)',(
                iso(now_ist()),outcome['preset'],outcome['location']['id'],
                json.dumps(outcome['actions']),json.dumps(outcome['inputs']),json.dumps(outcome),
                outcome['before']['health_score'],outcome['after']['health_score'],outcome['baseline']['source']))
            outcome['scenario_id']=cursor.lastrowid
    else:
        outcome['scenario_id']=None
    return jsonify(outcome)

@bp.get('/api/twin/history')
def history():
    location=request.args.get('location_id','').strip()
    if location and location not in {r['id'] for r in LOCATIONS}:
        return jsonify(error='Unknown monitoring location'),400
    day=request.args.get('date','').strip()
    if day:
        try: date.fromisoformat(day)
        except ValueError: return jsonify(error='Use YYYY-MM-DD date'),400
    q='SELECT id,created_at,preset,location_id,actions,health_before,health_after,baseline_source FROM twin_scenarios WHERE 1=1'
    args=[]
    if location: q+=' AND location_id=?'; args.append(location)
    if day: q+=' AND substr(created_at,1,10)=?'; args.append(day)
    q+=' ORDER BY id DESC LIMIT 150'
    with db.conn() as c:
        rows=[dict(r) for r in c.execute(q,args)]
    for row in rows:
        row['actions']=json.loads(row['actions'])
        with db.conn() as conn:
            raw=conn.execute('SELECT result_json FROM twin_scenarios WHERE id=?',(row['id'],)).fetchone()
        economics=(json.loads(raw['result_json']).get('economic_impact') or {}) if raw else {}
        row['revenue_at_risk_inr']=(economics.get('before') or {}).get('business_revenue_at_risk_inr')
        row['potential_revenue_protected_inr']=economics.get('potential_revenue_protected_inr')
    return jsonify(rows=rows)

@bp.get('/api/twin/history/<int:scenario_id>')
def history_detail(scenario_id):
    with db.conn() as c:
        row=c.execute('SELECT result_json FROM twin_scenarios WHERE id=?',(scenario_id,)).fetchone()
    return jsonify(json.loads(row['result_json'])) if row else (jsonify(error='Scenario not found'),404)

@bp.get('/api/twin/export.csv')
def export_csv():
    out=io.StringIO(); w=csv.writer(out)
    w.writerow(['ID','Time (IST)','Preset','Location','Actions','Health before (SIMULATED)','Health after (SIMULATED)','Traffic baseline type','Business revenue at risk before (INR, SIMULATED)','Business revenue at risk after (INR, SIMULATED)','Potential revenue protected (INR, SIMULATED)','Gross economic exposure avoided (INR, SIMULATED)','Intervention cost (INR, ASSUMED)','Net economic exposure avoided (INR, SIMULATED)'])
    with db.conn() as c:
        rows=c.execute('SELECT id,created_at,preset,location_id,actions,health_before,health_after,baseline_source,result_json FROM twin_scenarios ORDER BY id DESC LIMIT 1000').fetchall()
    for row in rows:
        w.writerow([row['id'],row['created_at'],row['preset'],row['location_id'],
                    ', '.join(json.loads(row['actions'])),row['health_before'],row['health_after'],row['baseline_source'],*economic_export_fields(row)])
    return Response(out.getvalue(),mimetype='text/csv',headers={'Content-Disposition':'attachment; filename=citysync_simulated_scenarios.csv'})


def economic_export_fields(row):
    """Handle older simulation rows created before economic modeling."""
    try:
        result=json.loads(row['result_json'])
        impact=result.get('economic_impact') or {}
        before=impact.get('before') or {}; after=impact.get('after') or {}
        return [before.get('business_revenue_at_risk_inr',''),
                after.get('business_revenue_at_risk_inr',''),
                impact.get('potential_revenue_protected_inr',''),
                impact.get('gross_exposure_avoided_inr',''),
                after.get('intervention_cost_inr',''),
                impact.get('net_exposure_avoided_inr','')]
    except (ValueError,TypeError): return ['']*6


@bp.post('/api/twin/spatial-intelligence')
def spatial_intelligence():
    try:
        observations={x['id']:x for x in ops_intelligence._snapshots()}
        payload=request.get_json(silent=True)
        weather=None
        if isinstance(payload,dict) and payload.get('mode')=='auto':
            weather=weather_service.area_weather(LOCATIONS)
            if weather['status']!='OBSERVED_API':
                return jsonify(error='Live weather is unavailable right now; switch to manual mode.'),503
        result=advanced_intelligence.analyze(payload, observations, (weather or {}).get('areas'))
        if weather: result['weather']={k:weather[k] for k in ('status','source','source_url','note')}
        return jsonify(result)
    except (ValueError, TypeError) as exc:
        return jsonify(error=str(exc)), 400
