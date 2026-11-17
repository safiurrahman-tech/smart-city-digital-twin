"""Automatic, area- and history-aware inputs for the economic exposure model.

These values REPLACE hand-typed assumptions. They are still illustrative: the area
weights are project-team assumptions (see advanced_intelligence.ZONE_ASSUMPTIONS) and the
history term uses only traffic speed ratios this app has itself recorded from TomTom.
No city revenue, footfall or trip-count dataset is connected, so results are modeled
exposure, never measured losses.
"""
from __future__ import annotations
from datetime import datetime
import db
from advanced_intelligence import ZONE_ASSUMPTIONS, IST, _hour
from locations import BY_ID

SOURCE_FULL = 'AREA_PROFILE_AND_TRAFFIC_HISTORY'
SOURCE_PROFILE = 'AREA_PROFILE_ONLY'


def _trip_factor(h):
    if 8 <= h <= 10 or 17 <= h <= 20: return 1.0
    if 11 <= h <= 16: return .75
    if 6 <= h <= 7 or 21 <= h <= 22: return .55
    return .25


def _business_factor(h):
    if 10 <= h <= 17: return 1.0
    if 8 <= h <= 9 or 18 <= h <= 20: return .6
    if 6 <= h <= 7 or 21 <= h <= 22: return .25
    return .08


def _history(location_id, lat, lon, hour):
    """Mean recorded speed ratio (all hours, and the hours within +/-1 of `hour`)."""
    with db.conn() as c:
        rows = c.execute("SELECT value, collected_at FROM readings WHERE module='traffic' AND metric='speed_ratio' "
                         "AND location_id=? AND lat=? AND lon=? AND value IS NOT NULL "
                         "ORDER BY collected_at DESC LIMIT 800", (location_id, lat, lon)).fetchall()
        try:
            runs = c.execute('SELECT COUNT(*) n FROM twin_scenarios WHERE location_id=?', (location_id,)).fetchone()['n']
        except Exception:
            runs = 0
    values = [(float(r['value']), str(r['collected_at'])) for r in rows]
    near = []
    for v, ts in values:
        try: hh = int(ts[11:13])
        except ValueError: continue
        if min((hh - hour) % 24, (hour - hh) % 24) <= 1: near.append(v)
    pool = near if len(near) >= 8 else [v for v, _ in values]
    if len(pool) < 3:
        return {'samples': len(values), 'same_hour_samples': len(near), 'mean_speed_ratio': None,
                'factor': 1.0, 'saved_scenario_runs': runs}
    mean = sum(pool) / len(pool)
    delay_fraction = max(0.0, 1.0 - mean)
    # Chronically congested corridors carry more exposed trips. Bounded, illustrative.
    factor = min(1.35, max(0.85, 1 + 1.2 * (delay_fraction - 0.10)))
    return {'samples': len(values), 'same_hour_samples': len(near), 'mean_speed_ratio': round(mean, 3),
            'factor': round(factor, 3), 'saved_scenario_runs': runs}


def derive(location_id, hour=None):
    """Return economic inputs for one monitored area at a Bengaluru hour. Raises KeyError if unknown."""
    loc = BY_ID[location_id]
    h = datetime.now(IST).hour if hour in (None, '') else _hour(hour)
    a = ZONE_ASSUMPTIONS[location_id]
    hist = _history(location_id, loc['lat'], loc['lon'], h)
    tf, bf = _trip_factor(h), _business_factor(h)
    base_trips = 900 + 3200 * (.55 * a['business'] + .45 * a['residential'])
    trips = round(base_trips * tf * hist['factor'], -1)
    activity = round((60000 + 480000 * a['business']) * bf, -3)
    value_of_time = round(100 + 70 * a['business'])
    return {
        'location_id': location_id, 'location': loc['name'], 'hour': h,
        'values': {'affected_trips_per_hour': max(0, trips), 'value_of_time_inr_hour': value_of_time,
                   'business_activity_inr_hour': max(0, activity)},
        'basis': {'area_weights': {'business': a['business'], 'residential': a['residential']},
                  'hour_factor_trips': tf, 'hour_factor_business': bf, 'history': hist},
        'source': SOURCE_FULL if hist['mean_speed_ratio'] is not None else SOURCE_PROFILE,
        'disclaimer': 'Modeled inputs from area weights, time of day and this app\'s own recorded TomTom speed history. '
                      'Not measured revenue, trip counts or official statistics.'}
