"""CitySync 3.0: reproducible, explicitly synthetic cross-system digital-twin model.

Measured TomTom speeds can anchor a segment; everything changed by the scenario
is hypothetical. Synthetic RandomForest is only validated against its own synthetic
training generator and is NEVER presented as a measured Bengaluru forecast.
"""
from __future__ import annotations
import math
from functools import lru_cache
from dataclasses import dataclass
from typing import Any

PRESETS = {
    'heavy_rain': {'name':'Monsoon cloudburst','rainfall_mm_h':95,'water_level_pct':82,'drainage_capacity_pct':48,'electricity_load_pct':91,'traffic_demand_pct':110,'leak_pct':6,'duration_min':60},
    'traffic_surge': {'name':'Peak-hour traffic surge','rainfall_mm_h':6,'water_level_pct':42,'drainage_capacity_pct':85,'electricity_load_pct':103,'traffic_demand_pct':175,'leak_pct':4,'duration_min':45},
    'power_surge': {'name':'Electricity demand spike','rainfall_mm_h':5,'water_level_pct':40,'drainage_capacity_pct':88,'electricity_load_pct':143,'traffic_demand_pct':114,'leak_pct':3,'duration_min':40},
    'pipe_leak': {'name':'Major water main leakage','rainfall_mm_h':8,'water_level_pct':30,'drainage_capacity_pct':83,'electricity_load_pct':93,'traffic_demand_pct':106,'leak_pct':66,'duration_min':80},
    'compound': {'name':'Compound infrastructure failure','rainfall_mm_h':120,'water_level_pct':93,'drainage_capacity_pct':35,'electricity_load_pct':147,'traffic_demand_pct':166,'leak_pct':54,'duration_min':90},
    'baseline': {'name':'Normal conditions','rainfall_mm_h':4,'water_level_pct':43,'drainage_capacity_pct':92,'electricity_load_pct':79,'traffic_demand_pct':100,'leak_pct':3,'duration_min':45},
}
# Economic exposure assumptions are editable demo inputs, not city accounts or reported losses.
ECON_DEFAULTS = {
    'affected_trips_per_hour': 1800,
    'value_of_time_inr_hour': 130,
    'business_activity_inr_hour': 325000,
}
ECON_SPECS = {
    'affected_trips_per_hour': (0, 100000),
    'value_of_time_inr_hour': (0, 5000),
    'business_activity_inr_hour': (0, 100000000),
}
ACTION_COSTS_INR = {
    'clear_drains': 8500, 'traffic_diversion': 4500, 'grid_backup': 7000,
    'demand_response': 1800, 'isolate_leak': 6000, 'public_warning': 900,
}

ACTIONS = {
    'clear_drains': {'name':'Deploy drain-clearing teams','effect':'Increase assumed drainage capacity by 28 points'},
    'traffic_diversion': {'name':'Traffic diversion & junction control','effect':'Lower assumed road demand by 28 points'},
    'grid_backup': {'name':'Traffic-signal backup power','effect':'Prevent assumed grid-to-signal cascade'},
    'demand_response': {'name':'Demand response / load shift','effect':'Reduce assumed electricity load by 27 points'},
    'isolate_leak': {'name':'Isolate leaking pipeline segment','effect':'Reduce assumed leakage by 38 points'},
    'public_warning': {'name':'Issue public advisory','effect':'Reduce assumed exposure, not infrastructure physics'},
}
SPECS = {
    'rainfall_mm_h': (0, 250), 'water_level_pct': (0, 100),
    'drainage_capacity_pct': (0, 100), 'electricity_load_pct': (0, 200),
    'traffic_demand_pct': (40, 240), 'leak_pct': (0, 100),
    'duration_min': (5, 240),
}

def clamp(n, minimum=0.0, maximum=100.0):
    return max(minimum, min(maximum, float(n)))

def _physics(x):
    """Assumed influence coefficients, NOT calibrated city engineering data."""
    rain, water, drain, power, traffic, leak = (x[k] for k in (
        'rainfall_mm_h','water_level_pct','drainage_capacity_pct',
        'electricity_load_pct','traffic_demand_pct','leak_pct'))
    # Water accumulation / drainage capacity as an illustrative risk index.
    flood = clamp((0.80*rain + 0.48*water - 0.52*drain - 4) * 1.16)
    grid = clamp((power - 88) * 2.42)
    shortage = clamp(leak * 0.86 + (100 - water) * 0.17 + grid * 0.16)
    signal_penalty = grid * 0.21 if power > 115 else grid * 0.08
    congestion = clamp((traffic - 85)*0.48 + flood*0.51 + signal_penalty)
    return dict(flood=flood, grid=grid, water=shortage, congestion=congestion,
                signal_penalty=signal_penalty)

@lru_cache(maxsize=1)
def _model():
    """ML surrogate on synthetic scenarios; withheld synthetic validation only.

    The RF adds non-linear interpolation but cannot validate real-world risk.
    """
    try:
        import numpy as np
        from sklearn.ensemble import RandomForestRegressor
        from sklearn.metrics import mean_absolute_error
        from sklearn.model_selection import train_test_split
        rng = np.random.default_rng(41)
        keys = tuple(SPECS)[:6]
        values = []
        labels = []
        for _ in range(1200):
            x = {k: float(rng.uniform(*SPECS[k])) for k in keys}
            x['duration_min'] = 45
            y = _physics(x)
            values.append([x[k] for k in keys]); labels.append([y['flood'],y['congestion'],y['grid'],y['water']])
        Xtr,Xte,ytr,yte = train_test_split(values,labels,test_size=.2,random_state=13)
        model = RandomForestRegressor(n_estimators=70,max_depth=13,min_samples_leaf=2,
                                      random_state=13,n_jobs=1)
        model.fit(Xtr,ytr)
        mae = mean_absolute_error(yte,model.predict(Xte),multioutput='raw_values')
        return model, keys, [round(float(v),2) for v in mae]
    except (ImportError, ValueError):
        return None, (), None

def model_card():
    model,_,mae = _model()
    return {
        'model':'RandomForest synthetic surrogate' if model is not None else 'Transparent rule-only fallback',
        'training':'1,200 artificially generated scenarios from disclosed rules' if model is not None else 'No sklearn dependency available',
        'validated_on':'240 withheld SYNTHETIC examples; no field calibration or external validation' if model is not None else 'No statistical validation',
        'synthetic_mae':dict(zip(('flood','congestion','grid','water'),mae)) if mae else None,
        'confidence':'DEMO_ONLY', 'claims':'Not a real-world forecast or probability. Risk scores are relative indices based on assumptions.'
    }

def _predict(x):
    model,keys,_ = _model()
    if model is None:
        return _physics(x), 'rule-based demo'
    try:
        raw = model.predict([[x[k] for k in keys]])[0]
        predicted = {key: clamp(raw[i]) for i,key in enumerate(('flood','congestion','grid','water'))}
        predicted['signal_penalty'] = _physics(x)['signal_penalty']
        return predicted, 'synthetic-data RandomForest'
    except (ValueError, TypeError):
        return _physics(x), 'rule-based fallback'

def validate(payload: Any, allowed_locations):
    if not isinstance(payload,dict): raise ValueError('Send a JSON scenario object.')
    preset = payload.get('preset','heavy_rain')
    if preset not in PRESETS: raise ValueError('Unknown scenario preset.')
    location_id = payload.get('location_id','silk_board')
    if location_id not in allowed_locations: raise ValueError('Unknown Bengaluru monitoring point.')
    options = payload.get('actions',[])
    if not isinstance(options,list) or len(options)>len(ACTIONS) or any(not isinstance(v,str) or v not in ACTIONS for v in options):
        raise ValueError('Unknown preventive action.')
    options = list(dict.fromkeys(options))
    x = {k:float(v) for k,v in PRESETS[preset].items() if k in SPECS}
    for k,limits in SPECS.items():
        if k in payload:
            if isinstance(payload[k],bool): raise ValueError(f'Invalid numeric value: {k}')
            try: n=float(payload[k])
            except (TypeError,ValueError): raise ValueError(f'Invalid numeric value: {k}')
            if not math.isfinite(n) or not limits[0]<=n<=limits[1]:
                raise ValueError(f'{k} must be between {limits[0]} and {limits[1]}.')
            x[k]=n
    for k, limits in ECON_SPECS.items():
        raw = payload.get(k, ECON_DEFAULTS[k])
        if isinstance(raw, bool): raise ValueError(f'Invalid economic assumption: {k}')
        try: n = float(raw)
        except (TypeError, ValueError): raise ValueError(f'Invalid economic assumption: {k}')
        if not math.isfinite(n) or not limits[0] <= n <= limits[1]:
            raise ValueError(f'{k} must be between {limits[0]} and {limits[1]}.')
        x[k] = n
    return preset,location_id,x,options

def _level(score):
    return 'CRITICAL' if score >= 75 else 'HIGH' if score >= 52 else 'WATCH' if score >= 28 else 'LOW'

def economic_impact(risk, inputs, actions=()):
    """Illustrative *economic exposure*, NOT measured losses, taxes, GDP or audited revenue.

    Traffic time cost and business revenue at risk are deliberately reported apart.
    The combined number is a modeled scenario comparison only.
    """
    hours = inputs['duration_min'] / 60.0
    trips = inputs['affected_trips_per_hour']
    time_value = inputs['value_of_time_inr_hour']
    turnover = inputs['business_activity_inr_hour']
    # At maximum congestion index, assume up to 20 additional minutes per trip.
    delay_hours_per_trip = (risk['congestion'] / 100.0) / 3.0
    mobility_cost = trips * hours * time_value * delay_hours_per_trip
    # Fraction of turnover exposed across three independently modeled disruptions.
    # Coefficients are illustrative, not derived from Bengaluru business surveys.
    revenue_fraction = min(0.90, 0.34*risk['flood']/100 +
                           0.42*risk['grid']/100 + 0.24*risk['water']/100)
    if 'public_warning' in actions: revenue_fraction *= 0.88
    revenue_risk = turnover * hours * revenue_fraction
    intervention_cost = sum(ACTION_COSTS_INR[a] for a in actions)
    return {
        'mobility_time_cost_inr': round(mobility_cost),
        'business_revenue_at_risk_inr': round(revenue_risk),
        'gross_economic_exposure_inr': round(mobility_cost + revenue_risk),
        'intervention_cost_inr': intervention_cost,
        'assumed_delay_min_per_trip': round(delay_hours_per_trip * 60, 1),
        'revenue_exposure_fraction_pct': round(revenue_fraction*100, 1),
    }

def simulate(payload, locations, traffic_readings=None):
    ids = {v['id']:v for v in locations}
    preset,loc_id,before,actions = validate(payload,ids)
    after = dict(before)
    if 'clear_drains' in actions: after['drainage_capacity_pct'] = clamp(after['drainage_capacity_pct']+28)
    if 'traffic_diversion' in actions: after['traffic_demand_pct'] = clamp(after['traffic_demand_pct']-28,40,240)
    if 'demand_response' in actions: after['electricity_load_pct'] = clamp(after['electricity_load_pct']-27,0,200)
    if 'isolate_leak' in actions: after['leak_pct'] = clamp(after['leak_pct']-38)
    first,engine = _predict(before)
    second,_ = _predict(after)
    # All configured actions are non-harmful by definition in this toy model.
    # The synthetic RF surrogate can violate this when interpolating nearby
    # synthetic points, so prevent its sampling noise from turning an assumed
    # mitigation into a new unrelated deterioration. Not a real-world claim.
    for dimension in ('flood', 'congestion', 'grid', 'water'):
        second[dimension] = min(first[dimension], second[dimension])
    if 'grid_backup' in actions:
        # Backup keeps traffic signal functional: remove illustrative signal-related congestion.
        second['congestion'] = clamp(second['congestion']-second['signal_penalty'])
    economics_before = economic_impact(first, before, ())
    economics_after = economic_impact(second, before, actions)
    gross_avoided = economics_before['gross_economic_exposure_inr'] - economics_after['gross_economic_exposure_inr']
    economic_summary = {
        'before': economics_before, 'after': economics_after,
        'potential_revenue_protected_inr': economics_before['business_revenue_at_risk_inr'] - economics_after['business_revenue_at_risk_inr'],
        'gross_exposure_avoided_inr': gross_avoided,
        'net_exposure_avoided_inr': gross_avoided - economics_after['intervention_cost_inr'],
        'assumptions': {**{k:before[k] for k in ECON_SPECS},'event_duration_min':before['duration_min'],
            'full_congestion_index_delay_min_per_trip':20,
            'revenue_exposure_weights': {'flood':0.34,'grid':0.42,'water':0.24},
            'intervention_costs_inr':{a:ACTION_COSTS_INR[a] for a in actions}},
        'provenance':'SYNTHETIC_ECONOMIC_ASSUMPTIONS',
        'disclaimer':'Illustrative potential economic exposure and business revenue at risk in INR, not measured revenue, losses, GDP, fiscal impact, or a finance forecast. Inputs and coefficients are assumptions; no city economic dataset is connected.'
    }
    loc = ids[loc_id]
    readings = traffic_readings or {}
    observation = readings.get(loc_id) or {}
    status=observation.get('status','UNAVAILABLE')
    measured=status=='LIVE' and isinstance(observation.get('speed_ratio'),(int,float))
    ratio=clamp(observation['speed_ratio']*100,1,100) if measured else 78.0
    obs_label='LIVE_TOMTOM_SEGMENT' if measured else 'SYNTHETIC_DEMO_BASELINE'
    congestion_before = clamp((100-ratio)*0.45+first['congestion']*0.65)
    congestion_after = clamp((100-ratio)*0.45+second['congestion']*0.65)
    def score(x):
        return round(clamp(100-(x['flood']*.28 + x['congestion']*.32 + x['grid']*.23 + x['water']*.17)),1)
    def metrics(x):
        return {k:round(float(x[k]),1) for k in ('flood','congestion','grid','water')}
    affected=[]
    for idx,p in enumerate(locations):
        if p['id']==loc_id or (first['flood']>=52 and idx%3==0) or (first['grid']>=75 and idx%4==0):
            affected.append({'id':p['id'],'name':p['name'],'lat':p['lat'],'lon':p['lon'],
                             'risk':round(first['flood']*.6+first['congestion']*.4 if p['id']==loc_id else (first['flood']*.42+first['grid']*.17),1)})
    links=[
       {'from':'Rainfall','to':'Drainage','effect':'Higher inflow increases assumed overflow index','active':before['rainfall_mm_h']>40},
       {'from':'Drainage','to':'Roads','effect':'Assumed surface flooding reduces road capacity','active':first['flood']>30},
       {'from':'Electricity','to':'Traffic signals','effect':'Grid overload can interrupt assumed signal operations','active':first['grid']>55},
       {'from':'Signals','to':'Congestion','effect':'Signal failure adds assumed congestion; backup can mitigate it','active':first['grid']>55},
       {'from':'Pipeline','to':'Water supply','effect':'Assumed leakage reduces usable supply','active':before['leak_pct']>20},
       {'from':'Electricity','to':'Water pumps','effect':'Loss of power could disrupt pumps without backup','active':first['grid']>75},
    ]
    risk_names={'flood':'Drainage overflow','congestion':'Traffic congestion','grid':'Electricity overload','water':'Water supply shortage'}
    alerts=[]
    for k,name in risk_names.items():
        level=_level(first[k])
        if level!='LOW':
            alerts.append({'id':k,'title':name,'severity':level,'risk_score':round(first[k],1),
                           'location':loc['name'],'origin':'SIMULATED','detail':f'{name} index is {round(first[k])}/100 under assumed {PRESETS[preset]["name"].lower()} conditions.'})
    alerts.sort(key=lambda a:-a['risk_score'])
    recommendations=[]
    ranked=[('clear_drains',first['flood']),('traffic_diversion',first['congestion']),('grid_backup',first['grid']),
            ('demand_response',first['grid']*.9),('isolate_leak',first['water']),('public_warning',max(first.values()))]
    for action,v in sorted(ranked,key=lambda e:-e[1]):
        if v>=25:
            recommendations.append({'id':action,'title':ACTIONS[action]['name'],'why':ACTIONS[action]['effect'],
                                    'applied':action in actions,'priority':_level(v)})
    explanation=[]
    if before['rainfall_mm_h']>=40: explanation.append(f"Rainfall is assumed at {before['rainfall_mm_h']:g} mm/h, putting pressure on modeled drainage capacity.")
    if first['flood']>=28: explanation.append('High assumed runoff can lower road capacity and increase congestion near the selected area.')
    if first['grid']>=28: explanation.append('Assumed electricity loading adds potential grid stress; no BESCOM demand telemetry is available.')
    if before['leak_pct']>=20: explanation.append('The hypothetical leak reduces effective water delivery and may create localized supply risk.')
    if not explanation: explanation=['The entered scenario is within the low-risk region of the synthetic model.']
    return {'preset':preset,'preset_name':PRESETS[preset]['name'],'location':loc,
            'engine':engine,'provenance':'SIMULATED_SCENARIO','baseline':{
                'source':obs_label,'speed_ratio_pct':round(ratio,1),'speed_kmh':observation.get('speed') if measured else None,
                'collected_at':observation.get('collected_at') if measured else None,
                'note':'Observed TomTom speed is a nearest-road-segment anchor; all downstream impacts are hypothetical.' if measured
                        else 'No suitable live segment reading; 78% is a fictional teaching baseline.'},
            'inputs':before,'intervention_inputs':after,'actions':actions, 'economic_impact':economic_summary,
            'before':{'risk':metrics(first),'health_score':score(first),'congestion_index':round(congestion_before,1)},
            'after':{'risk':metrics(second),'health_score':score(second),'congestion_index':round(congestion_after,1)},
            'improvement':{'health_points':round(score(second)-score(first),1),
                           'congestion_index_points':round(congestion_before-congestion_after,1),
                           'flood_index_points':round(first['flood']-second['flood'],1)},
            'alerts':alerts,'recommendations':recommendations[:6], 'links':links,'affected':affected,
            'explanation':explanation,
            'model_card':model_card(),
            'disclaimer':'What-if outputs are synthetic risk indices, not validated forecasts, probabilities, official alerts, or measured minutes saved.'}
