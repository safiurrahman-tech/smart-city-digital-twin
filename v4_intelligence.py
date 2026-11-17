"""CitySync 4 evidence-aware automatic risk screening and chart datasets.

No invented electricity or water sensor values. Forecast risk indices are heuristic
screenings, not calibrated probabilities or verified damage predictions.
"""
from datetime import datetime, timedelta
from data_normalizer import iso, now_ist
from locations import LOCATIONS
import ops_intelligence, weather_service


def _num(v):
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _score(rain_max, antecedent, speed_ratio):
    """Explainable demo-scale vulnerability index (0-100), NOT a probability."""
    rain = min(55, max(0, rain_max) * 1.4)
    wet = min(25, max(0, antecedent) * .25)
    traffic = min(20, max(0, (1 - speed_ratio) * 40)) if speed_ratio is not None else 0
    return round(min(100, rain + wet + traffic), 1)


def automatic_report(weather=None, places=None):
    if places is None:
        places = ops_intelligence._snapshots()
    if weather is None:
        weather = weather_service.area_weather(LOCATIONS)
    weather_areas = weather.get('areas', {}) if weather.get('status') == 'OBSERVED_API' else {}
    zones=[]; alerts=[]
    for p in places:
        w=weather_areas.get(p['id']) or {}
        rain=_num(w.get('rain_next3h_max_mm_h'))
        rainnow=_num(w.get('rain_now_mm_h'))
        antecedent=_num(w.get('antecedent_24h_mm'))
        observed_ratio=_num(p.get('speed_ratio')) if p.get('status')=='LIVE' else None
        risk=_score(rain, antecedent or 0, observed_ratio) if rain is not None else None
        evidence=[]
        if rain is not None:
            evidence.append(f'Max hourly model-forecast rain in next 3h: {rain:.1f} mm/h')
        if observed_ratio is not None:
            evidence.append(f'TomTom speed/free-flow ratio: {observed_ratio:.2f}')
        if rain is None:
            level='UNAVAILABLE'
        elif rain >= 30 or (rain >= 15 and observed_ratio is not None and observed_ratio < .65):
            level='HIGH'
        elif rain >= 10 or risk >= 35:
            level='WATCH'
        else:
            level='NORMAL'
        if level in ('HIGH','WATCH'):
            alerts.append({
                'key':f"forecast-rain:{p['id']}:{level}", 'location_id':p['id'],
                'location':p['name'], 'severity':level,
                'kind':'WEATHER_RISK_ADVISORY', 'title':f'{level} rainfall/drainage advisory — {p["name"]}',
                'detail':'; '.join(evidence)+'. Drainage stress is a hypothetical screening, not a detected flood.',
                'source':'Open-Meteo model forecast'+(' + TomTom traffic' if observed_ratio is not None else ''),
                'action':'Review official alerts, inspect known flood-prone drains, and confirm road conditions.',
                'confidence':'UNVALIDATED_RULE', 'observed_at':w.get('observed_at'),
            })
        if observed_ratio is not None and observed_ratio < .60:
            alerts.append({'key':f'traffic:{p["id"]}:HIGH','location_id':p['id'],
                'location':p['name'],'severity':'HIGH','kind':'OBSERVED_TRAFFIC',
                'title':f'Observed road slowdown — {p["name"]}',
                'detail':f'Current TomTom speed is {observed_ratio*100:.0f}% of free-flow speed on a nearby segment.',
                'source':'TomTom Flow','action':'Verify incidents and consider traffic management review.',
                'confidence':'OBSERVED_SEGMENT','observed_at':p.get('collected_at')})
        zones.append({'id':p['id'],'name':p['name'],'lat':p['lat'],'lon':p['lon'],
            'status':level,'screening_index':risk,'score_unit':'HEURISTIC_INDEX_NOT_PROBABILITY',
            'rain_now_mm_h':rainnow,'rain_next3h_max_mm_h':rain,
            'antecedent_24h_mm':antecedent,
            'rain_future_hours':w.get('rain_future_hours',[]),
            'weather_at':w.get('observed_at'),
            'traffic_status':p.get('status'),'speed_ratio':observed_ratio,
            'traffic_collected_at':p.get('collected_at'),
            'evidence':evidence,
            'drainage_condition':'UNMEASURED — no live drain/chamber sensors',
            'electricity_demand':'UNAVAILABLE — no feeder measurement',
            'water_supply':'UNAVAILABLE — no BWSSB pressure/flow measurement',
            'recommendation':'Inspect drains and check traffic conditions' if level in ('HIGH','WATCH') else 'Continue evidence collection'})
    order={'HIGH':0,'WATCH':1,'NORMAL':2,'UNAVAILABLE':3}
    zones.sort(key=lambda x:(order[x['status']],-(x['screening_index'] or 0)))
    alerts.sort(key=lambda x:(0 if x['severity']=='HIGH' else 1, x['location']))
    return {'generated_at':iso(now_ist()), 'model':'EXPLAINABLE_SCREENING_V1',
            'model_validation':'NOT_VALIDATED_FOR_REAL_BENGALURU_INCIDENTS',
            'weather_status':weather.get('status'),'weather_source':weather.get('source'),
            'weather_note':weather.get('note'),'zones':zones,'active_alerts':alerts,
            'data_integrity':{'traffic':'Observed TomTom road segments only when LIVE',
                'weather':'Open-Meteo API-reported observations and model forecasts, not gauges at exact coordinates',
                'electricity':'No verified feeder demand; unavailable',
                'water':'No verified pipe pressure/chamber levels; unavailable',
                'risk':'Heuristic risk index; not probability or a trained prediction of actual damage'}}


def power_graph():
    return {'status':'UNAVAILABLE','source':'BESCOM / Karnataka SLDC public aggregate (not connected in this upload)',
            'observed':[],'forecast':[], 'note':'No authenticated/verified live electricity readings or time-series. No fabricated graph.'}


def water_graph(report):
    return {'status':'MODELED_SCREENING' if report['weather_status']=='OBSERVED_API' else 'UNAVAILABLE',
            'source':'Open-Meteo rain forecast + illustrative drainage stress screen',
            'areas':[{'name':z['name'],'rain_3h_peak_mm_h':z['rain_next3h_max_mm_h'],
                      'heuristic_drainage_index':z['screening_index']} for z in report['zones']],
            'note':'Not live BWSSB drainage, chamber, pipe or reservoir telemetry.'}


def evaluate_and_store():
    """Used by the independent scheduler and by the operations API.

    No source data is synthesized if collection fails.
    """
    import v4_security
    report=automatic_report()
    signal=v4_security.security_signal()
    if signal['severity']=='HIGH':
        report['active_alerts'].append({'key':'security:denied-access:HIGH',
            'kind':'SECURITY_ACCESS_ALERT','severity':'HIGH','location_id':None,
            'title':'Security review: repeated denied privileged access',
            'detail':f"{signal['denied_last_hour']} denied requests to protected endpoints in the past hour.",
            'source':'CitySync server security audit','action':'Review signed-in Security Operations page; check access logs.',
            'confidence':'OBSERVED_SERVER_DENIALS'})
    v4_security.reconcile(report['active_alerts'])
    report['security_signal']=signal
    report['alerts']=v4_security.alerts()
    return report
