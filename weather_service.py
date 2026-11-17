"""Optional Open-Meteo observed weather, with explicit failure rather than fake live data."""
from __future__ import annotations
import time
import requests
_cache={'expires':0,'result':None}

def current_weather():
    now=time.time()
    if _cache['expires']>now and _cache['result'] is not None:
        return _cache['result']
    url='https://api.open-meteo.com/v1/forecast'
    params={'latitude':12.9716,'longitude':77.5946,
            'current':'temperature_2m,relative_humidity_2m,precipitation,rain,weather_code',
            'hourly':'precipitation_probability,precipitation',
            'timezone':'Asia/Kolkata','forecast_days':2}
    try:
        r=requests.get(url,params=params,timeout=5)
        r.raise_for_status(); raw=r.json(); c=raw['current']
        result={'status':'OBSERVED_API','source':'Open-Meteo','source_url':'https://open-meteo.com/',
                'coverage':'Bengaluru city-coordinate model/grid data, not ward-level flood measurement',
                'observed_at':c.get('time'),'temperature_c':c.get('temperature_2m'),
                'humidity_pct':c.get('relative_humidity_2m'),
                'precipitation_mm':c.get('precipitation'), 'rain_mm':c.get('rain'),
                'weather_code':c.get('weather_code'),
                'hourly':list(zip(raw.get('hourly',{}).get('time',[])[:18],
                                   raw.get('hourly',{}).get('precipitation_probability',[])[:18])),
                'note':'Weather data are API-reported, not direct flood or drainage telemetry.'}
        _cache.update(expires=now+600,result=result)
        return result
    except (requests.RequestException,ValueError,TypeError,KeyError) as exc:
        result={'status':'UNAVAILABLE','source':'Open-Meteo','observed_at':None,
                'temperature_c':None,'humidity_pct':None,'precipitation_mm':None,
                'hourly':[],'note':f'Weather API unavailable ({type(exc).__name__}). Scenario sliders still work offline.'}
        _cache.update(expires=now+60,result=result)
        return result


_area_cache={'expires':0,'result':None}

def parse_area(raw, locations):
    """Turn an Open-Meteo multi-point response into per-location planning inputs.

    rain_now_mm_h: precipitation reported for the current hour.
    rain_next3h_max_mm_h: highest forecast hourly precipitation over the next 3 hours.
    antecedent_24h_mm: precipitation total over the previous 24 hours (ground wetness proxy).
    """
    items=raw if isinstance(raw,list) else [raw]
    out={}
    for loc,item in zip(locations,items):
        cur=item['current']; hourly=item['hourly']
        times=hourly['time']; prec=[v or 0 for v in hourly['precipitation']]
        stamp=str(cur['time'])[:13]+':00'
        idx=times.index(stamp)
        out[loc['id']]={'temperature_c':cur.get('temperature_2m'),
            'rain_now_mm_h':float(cur.get('precipitation') or 0),
            'rain_next3h_max_mm_h':max(prec[idx+1:idx+4] or [0]),
            'antecedent_24h_mm':round(sum(prec[max(0,idx-24):idx]),1),
            'rain_future_hours':[{'time':t,'precipitation_mm':round(float(v or 0),2)}
                                  for t,v in zip(times[idx+1:idx+25],prec[idx+1:idx+25])],
            'observed_at':cur['time']}
    return out

def area_weather(locations):
    """Live per-area weather for all monitoring points in ONE keyless API call.

    Returns {'status':'OBSERVED_API'|'UNAVAILABLE', 'areas':{id:{...}}}. Never invents values.
    """
    now=time.time()
    if _area_cache['expires']>now and _area_cache['result'] is not None:
        return _area_cache['result']
    params={'latitude':','.join(str(l['lat']) for l in locations),
            'longitude':','.join(str(l['lon']) for l in locations),
            'current':'temperature_2m,precipitation','hourly':'precipitation',
            'past_days':1,'forecast_days':2,'timezone':'Asia/Kolkata'}
    try:
        r=requests.get('https://api.open-meteo.com/v1/forecast',params=params,timeout=8)
        r.raise_for_status()
        result={'status':'OBSERVED_API','source':'Open-Meteo','source_url':'https://open-meteo.com/',
                'areas':parse_area(r.json(),locations),
                'note':'Model/grid weather per monitoring point, not ward-level flood or drain telemetry.'}
        _area_cache.update(expires=now+600,result=result)
    except (requests.RequestException,ValueError,TypeError,KeyError) as exc:
        result={'status':'UNAVAILABLE','source':'Open-Meteo','areas':{},
                'note':f'Per-area weather unavailable ({type(exc).__name__}).'}
        _area_cache.update(expires=now+60,result=result)
    return result
