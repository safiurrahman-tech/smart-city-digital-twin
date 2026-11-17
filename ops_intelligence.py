"""CitySync operations intelligence: honest summaries, not inferred infrastructure telemetry.

Only recent TomTom observations count as observed traffic. BESCOM / BWSSB data is manually
sourced notices; alerts are advisory rule matches, never proof of causation.
"""
from __future__ import annotations
import math
from statistics import median, mean
import db, config
from data_normalizer import iso, now_ist, freshness, is_active, is_upcoming
from locations import get_locations


def _snapshots():
    result = []
    with db.conn() as c:
        for loc in get_locations():
            rows = [dict(r) for r in c.execute(
                "SELECT metric, value, collected_at, completeness FROM readings "
                "WHERE module='traffic' AND location_id=? AND lat=? AND lon=? "
                "ORDER BY collected_at DESC,id DESC LIMIT 120",
                (loc['id'], loc['lat'], loc['lon']))]
            if not rows:
                result.append({**loc, 'status':'UNAVAILABLE','reason':'No reading for this monitoring coordinate',
                               'speed_ratio':None, 'speed':None,'delay_s':None,'observed_at':None,'sample_count':0})
                continue
            stamp=rows[0]['collected_at']
            measured={r['metric']:r for r in rows if r['collected_at']==stamp}
            ratio=measured.get('speed_ratio',{}).get('value')
            speed=measured.get('current_speed',{}).get('value')
            delay=measured.get('delay',{}).get('value')
            status, age=freshness('LIVE',stamp,config.FLOW_INTERVAL_MIN)
            result.append({**loc,'status':status,'speed_ratio':ratio,'speed':speed,'delay_s':delay,
                           'collected_at':stamp,'age_seconds':age,'confidence':measured.get('current_speed',{}).get('completeness'),
                           'sample_count':sum(1 for r in rows if r['metric']=='current_speed')})
    return result


def summary():
    places=_snapshots()
    current=[p for p in places if p['status']=='LIVE' and isinstance(p['speed_ratio'],(int,float))]
    with db.conn() as c:
        notices=[dict(r) for r in c.execute('SELECT * FROM notices ORDER BY id DESC LIMIT 100')]
        incidents=c.execute('SELECT COUNT(*) AS n, MAX(collected_at) AS latest FROM incidents').fetchone()
        jobs=[dict(r) for r in c.execute('SELECT ts,job,ok,message FROM collector_log ORDER BY id DESC LIMIT 5')]
        hist=c.execute("SELECT COUNT(DISTINCT collected_at) AS snapshots, MIN(collected_at) AS oldest, MAX(collected_at) AS newest "
                       "FROM readings WHERE module='traffic' AND metric='current_speed'").fetchone()
        usage=[dict(r) for r in c.execute('SELECT * FROM api_usage ORDER BY period DESC LIMIT 5')]
    active=[n for n in notices if is_active(n)]
    upcoming=[n for n in notices if is_upcoming(n)]
    incident_status,_=freshness('LIVE',incidents['latest'],config.INCIDENT_INTERVAL_MIN) if incidents['latest'] else ('UNAVAILABLE',None)
    alerts=[]
    for p in current:
        r=p['speed_ratio']
        if r is not None and r<0.6:
            alerts.append({'severity':'HIGH','kind':'MEASURED_TRAFFIC','location_id':p['id'],
                           'title':f"Severe relative slowdown: {p['name']}",
                           'detail':f"TomTom speed is {round(r*100)}% of this segment's free-flow speed. Check nearby incidents.",
                           'evidence':'TomTom Flow · nearest matched segment','source_status':'LIVE'})
        elif r is not None and r<0.8:
            alerts.append({'severity':'WATCH','kind':'MEASURED_TRAFFIC','location_id':p['id'],
                           'title':f"Traffic slowdown: {p['name']}",
                           'detail':f"Current speed is {round(r*100)}% of the segment's free-flow speed.",
                           'evidence':'TomTom Flow · nearest matched segment','source_status':'LIVE'})
    for n in active:
        title=n.get('title') or ('Planned electricity outage' if n['module']=='electricity' else 'Water supply notice')
        alerts.append({'severity':'WATCH','kind':'OFFICIAL_NOTICE','location_id':n.get('location_id'),
                       'title':title, 'detail':f"{n['area_text']} · {n['source_name']}; a manually-entered, source-linked notice.",
                       'evidence':n.get('source_url'), 'source_status':'SCHEDULED'})
    rank={'HIGH':0,'WATCH':1,'INFO':2}
    alerts.sort(key=lambda v:rank.get(v['severity'],9))
    metrics={
        'traffic_live':len(current), 'traffic_total':len(places),
        'mean_speed_ratio':round(mean(p['speed_ratio'] for p in current),3) if current else None,
        'worst_segment':min(current,key=lambda p:p['speed_ratio'])['name'] if current else None,
        'incident_records':incidents['n'], 'incident_status':incident_status,
        'active_official_notices':len(active),'upcoming_official_notices':len(upcoming),
        'snapshots_collected':hist['snapshots'] or 0,
    }
    readiness=[
        {'name':'Traffic collection','state':'AVAILABLE' if current else 'NEEDS_DATA',
         'detail':f"{len(current)}/{len(places)} road-segment readings live"},
        {'name':'Traffic incident feed','state':'AVAILABLE' if incident_status=='LIVE' else 'NEEDS_DATA',
         'detail':f"{incidents['n']} city-wide records, latest {incidents['latest'] or 'not collected'}"},
        {'name':'Electricity demand telemetry','state':'UNAVAILABLE','detail':'No verified live BESCOM grid-load feed; model uses hypothetical load'},
        {'name':'Water telemetry','state':'UNAVAILABLE','detail':'No verified live BWSSB pressure / flow feed; notices are manually entered'},
        {'name':'Decision model','state':'SIMULATED','detail':'Rule-based, disclosed assumptions; not calibrated prediction'},
        {'name':'Traffic history','state':'AVAILABLE' if metrics['snapshots_collected']>=4 else 'NEEDS_DATA',
         'detail':f"{metrics['snapshots_collected']} distinct collection timestamps"},
    ]
    return {'generated_at':iso(now_ist()),'metrics':metrics,'locations':places,'alerts':alerts,
            'readiness':readiness,'collector_jobs':jobs,'api_usage':usage,
            'history':{'oldest':hist['oldest'],'newest':hist['newest'],'snapshots':hist['snapshots'] or 0},
            'caveat':'Observed traffic is nearest TomTom road segments. Electricity and water are source-linked notices, not real-time grid/water telemetry.'}


def trend(location_id):
    """Exploratory linear projection only when enough genuinely collected readings exist.

    Uses the last 24 distinct current-speed/free-flow-speed observations and an 80/20
    chronological validation. An unsupported forecast has no numeric value.
    """
    from locations import BY_ID
    if location_id not in BY_ID:
        raise KeyError(location_id)
    loc=BY_ID[location_id]
    with db.conn() as c:
        rows=c.execute("SELECT collected_at,value FROM readings WHERE module='traffic' AND metric='speed_ratio' "
                       "AND location_id=? AND lat=? AND lon=? AND value IS NOT NULL "
                       "ORDER BY collected_at DESC,id DESC LIMIT 40",(location_id,loc['lat'],loc['lon'])).fetchall()
    seen={}
    for r in rows:seen[r['collected_at']]=r['value']
    points=sorted(seen.items())[-24:]
    data={'location_id':location_id,'name':loc['name'],'samples':len(points),
          'label':'EXPLORATORY TREND ONLY — not a validated operational forecast',
          'source':'TomTom speed ratios collected by this application'}
    if len(points)<12:
        return {**data,'status':'INSUFFICIENT_HISTORY', 'reason':'At least 12 distinct, time-spaced readings needed for exploratory trend and holdout scoring.'}
    from datetime import datetime
    t0=datetime.fromisoformat(points[0][0]); last=datetime.fromisoformat(points[-1][0]); span=(last-t0).total_seconds()/60
    if span<60:
        return {**data,'status':'INSUFFICIENT_HISTORY','reason':'At least 60 minutes of collected history required; avoid projecting from rapid duplicate requests.'}
    x=[(datetime.fromisoformat(t)-t0).total_seconds()/60 for t,_ in points]
    y=[float(v) for _,v in points]
    def predict(xs, ys, at):
        xm=mean(xs); ym=mean(ys); d=sum((v-xm)**2 for v in xs)
        slope=sum((a-xm)*(b-ym) for a,b in zip(xs,ys))/d if d else 0
        return max(0,min(1.5,ym+slope*(at-xm)))
    cut=max(8,int(len(x)*0.8))
    errors=[abs(predict(x[:cut],y[:cut],xx)-yy) for xx,yy in zip(x[cut:],y[cut:])]
    projected=predict(x,y,x[-1]+15)
    return {**data,'status':'EXPERIMENTAL','span_minutes':round(span,1),
            'last_measured_ratio':round(y[-1],3),'projected_15m_ratio':round(projected,3),
            'holdout_mae_ratio':round(mean(errors),3), 'holdout_samples':len(errors),
            'assumption':'Linear extrapolation for the next 15 minutes; sample intervals may be uneven; cannot infer outages.'}
