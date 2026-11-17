"""Scenario-based municipal planning aides; no live grid/pipeline/ambulance telemetry.

The area allocations and asset vulnerability assumptions are illustrative, not
BESCOM/BWSSB engineering evidence. An emergency corridor is an *advisory*, never
an ambulance dispatch, traffic-light override or safe/fastest route claim.
"""
from __future__ import annotations
from datetime import datetime
import math
from typing import Mapping
from zoneinfo import ZoneInfo
from locations import LOCATIONS

IST = ZoneInfo('Asia/Kolkata')
# Publicly editable demonstration assumptions; NOT connected to infrastructure assets.
# All seven points are *traffic sampling sites*, not electrical feeder nodes.
ZONE_ASSUMPTIONS = {
    'silk_board': {'residential': 0.36, 'business': 0.86, 'critical': 0.70, 'rain_exposure': 0.78, 'asset_age': 0.64},
    'electronic_city': {'residential': 0.44, 'business': 0.94, 'critical': 0.49, 'rain_exposure': 0.57, 'asset_age': 0.45},
    'whitefield': {'residential': 0.68, 'business': 0.90, 'critical': 0.60, 'rain_exposure': 0.62, 'asset_age': 0.51},
    'kr_puram': {'residential': 0.75, 'business': 0.55, 'critical': 0.65, 'rain_exposure': 0.83, 'asset_age': 0.78},
    'hebbal': {'residential': 0.75, 'business': 0.68, 'critical': 0.87, 'rain_exposure': 0.73, 'asset_age': 0.58},
    'jayanagar': {'residential': 0.88, 'business': 0.53, 'critical': 0.77, 'rain_exposure': 0.48, 'asset_age': 0.69},
    'yelahanka': {'residential': 0.85, 'business': 0.44, 'critical': 0.60, 'rain_exposure': 0.54, 'asset_age': 0.43},
}

# Clearly SIMULATED localized storm for demonstrations when real weather is dry.
DEMO_STORM = {
    'kr_puram':        {'temperature_c':29,'rain_now_mm_h':48,'rain_next3h_max_mm_h':72,'antecedent_24h_mm':85},
    'hebbal':          {'temperature_c':29,'rain_now_mm_h':36,'rain_next3h_max_mm_h':55,'antecedent_24h_mm':60},
    'silk_board':      {'temperature_c':29,'rain_now_mm_h':30,'rain_next3h_max_mm_h':45,'antecedent_24h_mm':55},
    'whitefield':      {'temperature_c':29,'rain_now_mm_h':18,'rain_next3h_max_mm_h':30,'antecedent_24h_mm':35},
    'jayanagar':       {'temperature_c':29,'rain_now_mm_h':12,'rain_next3h_max_mm_h':20,'antecedent_24h_mm':25},
    'electronic_city': {'temperature_c':29,'rain_now_mm_h':6,'rain_next3h_max_mm_h':12,'antecedent_24h_mm':15},
    'yelahanka':       {'temperature_c':29,'rain_now_mm_h':4,'rain_next3h_max_mm_h':8,'antecedent_24h_mm':10},
}

def bounded(raw, name, low, high):
    if isinstance(raw, bool): raise ValueError(f'{name} must be a number')
    try: n = float(raw)
    except (TypeError, ValueError): raise ValueError(f'{name} must be a number')
    if not math.isfinite(n) or n < low or n > high:
        raise ValueError(f'{name} must be within {low}–{high}')
    return n

def _hour(value):
    if value in (None, ''): return datetime.now(IST).hour
    if isinstance(value, str) and len(value)==5 and value[2]==':':
        hh, mm = value.split(':')
        if not (hh.isdigit() and mm.isdigit() and 0<=int(hh)<24 and 0<=int(mm)<60):
            raise ValueError('Time must be HH:MM in Bengaluru time')
        return int(hh)
    n=bounded(value,'hour',0,23)
    if not n.is_integer(): raise ValueError('hour must be an integer')
    return int(n)

def _observed(p, observations):
    o=(observations or {}).get(p['id'], {})
    speed=o.get('speed_ratio')
    return {'ratio': round(speed, 3) if o.get('status')=='LIVE' and isinstance(speed,(int,float)) else None,
            'status':o.get('status','UNAVAILABLE'), 'observed_at':o.get('collected_at')}

def _auto_inputs(w, manual_rain, manual_water, manual_surge):
    """Derive per-area scenario inputs from live weather. Heuristics, labelled ESTIMATED."""
    if not w: return manual_rain, manual_water, manual_surge, 'MANUAL_FALLBACK'
    rain=min(250.0,max(w['rain_now_mm_h'],w['rain_next3h_max_mm_h']))
    water=min(100.0,10+1.1*w['antecedent_24h_mm']+4*w['rain_now_mm_h'])
    temp=w.get('temperature_c')
    surge=min(160.0,max(70.0,100+max(0,(temp if temp is not None else 28)-28)*3))
    return rain, water, surge, 'LIVE_WEATHER_ESTIMATE'

def analyze(payload: Mapping | None, observations=None, area_weather=None):
    if not isinstance(payload, dict): raise ValueError('Send a JSON object')
    rain=bounded(payload.get('rainfall_mm_h',65),'rainfall_mm_h',0,250)
    surge=bounded(payload.get('electricity_demand_pct',110),'electricity_demand_pct',0,200)
    water=bounded(payload.get('drainage_fill_pct',65),'drainage_fill_pct',0,100)
    hour=_hour(payload.get('hour'))
    mode=payload.get('mode','manual')
    if mode not in ('manual','auto','demo_storm'): raise ValueError("mode must be 'manual', 'auto' or 'demo_storm'")
    if mode=='demo_storm': area_weather=DEMO_STORM
    if mode=='auto' and not area_weather: raise ValueError('Auto mode needs live weather; use manual mode')
    ambulance=payload.get('ambulance',False)
    if not isinstance(ambulance,bool): raise ValueError('ambulance must be true or false')
    source=payload.get('ambulance_from','silk_board')
    target=payload.get('ambulance_to','hebbal')
    valid={p['id'] for p in LOCATIONS}
    if source not in valid or target not in valid: raise ValueError('Unknown emergency corridor endpoint')
    if ambulance and source==target: raise ValueError('Choose distinct endpoints for an emergency corridor')
    # Clear, deterministic hourly shape; simulated weights, not measured MWh or feeders.
    day_business=1.0 if 9<=hour<18 else .23
    evening_residential=1.0 if 18<=hour<=23 or 6<=hour<9 else .55
    zones=[]
    for p in LOCATIONS:
        assumptions=ZONE_ASSUMPTIONS[p['id']]
        observed=_observed(p,observations)
        if mode in ('auto','demo_storm'):
            rain_z,water_z,surge_z,src=_auto_inputs(area_weather.get(p['id']),rain,water,surge)
            if mode=='demo_storm': src='DEMO_STORM_SIMULATION'
        else: rain_z,water_z,surge_z,src=rain,water,surge,'MANUAL'
        demand=(surge_z*(.35+.37*assumptions['business']*day_business+.28*assumptions['residential']*evening_residential))
        critical=assumptions['critical']
        # Higher critical-infrastructure weight raises protection priority; does not mean
        # power can actually be transferred between distribution feeders.
        allocation_priority=round(min(100, demand*.36+critical*40),1)
        chamber=min(100,max(0, .47*rain_z+.34*water_z+.31*100*assumptions['rain_exposure']-27))
        pipeline=min(100,max(0,.24*rain_z+.18*water_z+43*assumptions['asset_age']+15*assumptions['rain_exposure']-26))
        roads=min(100,max(0,chamber*.59+rain_z*.13+(1-observed['ratio'])*25 if observed['ratio'] is not None else chamber*.59+rain_z*.13))
        outage=min(100,max(0,.7*rain_z+20*assumptions['asset_age']*min(1,rain_z/30)+.4*max(0,surge_z-100)))
        supply=min(100,max(0,.65*pipeline+.5*outage))
        zones.append({**p,'observed_traffic':observed,'demand_index':round(min(200,demand),1),
          'power_priority':allocation_priority,'power_band': 'PRIORITIZE' if allocation_priority>=70 else 'BALANCED' if allocation_priority>=50 else 'LOWER RELATIVE DEMAND',
          'chamber_overflow_risk':round(chamber,1),'pipeline_damage_risk':round(pipeline,1),
          'road_disruption_risk':round(min(100,roads),1),'power_outage_exposure':round(outage,1),'water_supply_risk':round(supply,1),
          'inputs_used':{'rain_now_mm_h':(area_weather or {}).get(p['id'],{}).get('rain_now_mm_h'),'rain_next3h_mm_h':(area_weather or {}).get(p['id'],{}).get('rain_next3h_max_mm_h'),'rainfall_mm_h':round(rain_z,1),'drainage_fill_pct':round(water_z,1),'electricity_demand_pct':round(surge_z,1),'source':src},'assumed_criticality':round(critical*100),
          'reason':f"Scenario demand varies with hour {hour:02}:00, local business/residential assumptions and critical-service priority. Rain and drainage affect chamber/pipe screening."})
    zones.sort(key=lambda z:-z['power_priority'])
    by_id={z['id']:z for z in zones}
    warnings=[]
    for zone in zones:
        if zone['chamber_overflow_risk']>=65:
            warnings.append({'location':zone['name'],'type':'DRAINAGE_CHAMBER','severity':'HIGH','score':zone['chamber_overflow_risk'],
               'action':'Prioritize field inspection and drain clearing; do not infer a confirmed overflow.'})
        if zone['pipeline_damage_risk']>=55:
            warnings.append({'location':zone['name'],'type':'PIPELINE_VULNERABILITY','severity':'WATCH','score':zone['pipeline_damage_risk'],
               'action':'Check pressure/inspection logs and dispatch qualified inspection if independently corroborated.'})
        if zone['power_outage_exposure']>=40:
            warnings.append({'location':zone['name'],'type':'POWER_OUTAGE_EXPOSURE','severity':'HIGH' if zone['power_outage_exposure']>=60 else 'WATCH','score':zone['power_outage_exposure'],
               'action':'Pre-position repair crews and protect essential services; this is exposure screening, not a confirmed outage.'})
        if zone['water_supply_risk']>=45:
            warnings.append({'location':zone['name'],'type':'WATER_SUPPLY_DISRUPTION','severity':'HIGH' if zone['water_supply_risk']>=60 else 'WATCH','score':zone['water_supply_risk'],
               'action':'Check pumping-station power backup and pipeline inspection logs; not a confirmed supply failure.'})
        if zone['power_priority']>=75:
            warnings.append({'location':zone['name'],'type':'POWER_PRIORITY','severity':'WATCH','score':zone['power_priority'],
               'action':'Review forecast feeder load and protect essential services; no automated grid switching.'})
    rain_rank=sorted(zones,key=lambda z:-max(z['chamber_overflow_risk'],z['pipeline_damage_risk'],z['road_disruption_risk']))
    rain_priority=[{'rank':i+1,'id':z['id'],'location':z['name'],
        'score':round(max(z['chamber_overflow_risk'],z['pipeline_damage_risk'],z['road_disruption_risk']),1),
        'rainfall_mm_h':z['inputs_used']['rainfall_mm_h'],
        'level':'HIGH' if z['chamber_overflow_risk']>=65 else 'ELEVATED' if max(z['chamber_overflow_risk'],z['pipeline_damage_risk'])>=40 else 'NORMAL'}
        for i,z in enumerate(rain_rank)]
    def _cat(key,high,watch):
        ranked=sorted(zones,key=lambda z:-z[key])
        hits=[{'id':z['id'],'location':z['name'],'score':z[key]} for z in ranked if z[key]>=watch]
        level='HIGH' if ranked[0][key]>=high else 'ELEVATED' if ranked[0][key]>=watch else 'NORMAL'
        return {'level':level,'areas':hits[:4],'ranking':[{'id':z['id'],'location':z['name'],'score':z[key]} for z in ranked]}
    categories={'drainage':_cat('chamber_overflow_risk',65,40),'electricity':_cat('power_outage_exposure',60,40),'water':_cat('water_supply_risk',60,45)}
    order={'NORMAL':0,'ELEVATED':1,'HIGH':2}
    alert_level=max((c['level'] for c in categories.values()),key=lambda l:order[l])
    route=None
    if ambulance:
        # We do not have a road graph or actual navigation ETA. Never call this a route or
        # claim ambulance location or green-signal control based on arbitrary sample pins.
        a,b=by_id[source],by_id[target]
        route={'from':a['name'],'to':b['name'],'requested_hour_ist':f'{hour:02}:00',
          'start': {'lat':a['lat'],'lon':a['lon']},'end': {'lat':b['lat'],'lon':b['lon']},
          'start_observed':a['observed_traffic'],'end_observed':b['observed_traffic'],
          'priority':'REQUEST HUMAN TRAFFIC CONTROL REVIEW',
          'advice':['Confirm origin/destination and exact patient transfer with dispatch',
                    'Check official routing/road closures and actual live navigation ETA',
                    'Coordinate authorized traffic police clearance; never assume automatic signal priority'],
          'eta_minutes':None,'route_geometry':None,'signal_override':False,
          'disclaimer':'Emergency planning exercise only. No ambulance GPS, connected traffic signals, road network routing, or dispatch integration.'}
    return {'generated_at':datetime.now(IST).isoformat(timespec='seconds'),
      'mode':mode,'alert_level':alert_level,'categories':categories,'rain_priority':rain_priority,
      'input':{'mode':mode,'rainfall_mm_h':rain,'electricity_demand_pct':surge,'drainage_fill_pct':water,'hour':hour,'ambulance':ambulance,'ambulance_from':source,'ambulance_to':target},
      'zones':zones,'warnings':sorted(warnings,key=lambda x:-x['score']),
      'emergency':route,'assumptions':{'training':'Deterministic rule-based spatial screening; NOT an ML model trained on local BESCOM/BWSSB assets',
        'power':'Dimensionless relative demand index; not MW/kWh nor a feeder load forecast',
        'underground':'Pipeline and drainage chamber conditions are unobserved; risk is a hypothetical inspection-priority index',
        'traffic':'TomTom can anchor sampled segment speed only where LIVE; cannot determine ambulance journey',
        'refresh':'Recomputed per request, with fresh stored traffic observations when available',
        'authority':'Never automatically control emergency vehicles, grid switching, or traffic signals'},
      'provenance':('LIVE_WEATHER_DRIVEN_RULE_SCREENING' if mode=='auto' else 'SIMULATED_DEMO_STORM' if mode=='demo_storm' else 'SIMULATED_PLANNING_WITH_OPTIONAL_TOMTOM_OBSERVATIONS')}
