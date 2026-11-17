"""Turns raw source payloads into one reading shape and decides the honest status label."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import config

IST = ZoneInfo(config.TZ)
STATUSES = ("LIVE", "DELAYED", "HISTORICAL", "SIMULATED", "UNAVAILABLE")

def now_ist():
    return datetime.now(IST)

def iso(dt):
    return dt.astimezone(IST).isoformat(timespec="seconds") if dt else None

def parse_ts(s):
    if not s:
        return None
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=IST)
    except ValueError:
        return None

def freshness(status, collected_at, interval_min, now=None):
    """Downgrade LIVE to DELAYED when the reading is older than STALE_FACTOR x interval.
    Static/scheduled/simulated labels are never upgraded to LIVE."""
    now = now or now_ist()
    t = parse_ts(collected_at)
    age_s = int((now - t).total_seconds()) if t else None
    if status == "LIVE" and (age_s is None or age_s > config.STALE_FACTOR * interval_min * 60):
        status = "DELAYED"
    return status, age_s

def congestion_level(current, free_flow):
    """Speed ratio -> severity. Thresholds are a project convention, not an official standard."""
    if not current or not free_flow:
        return None, "UNKNOWN"
    r = current / free_flow
    if r >= 0.8: sev = "FREE"
    elif r >= 0.6: sev = "LIGHT"
    elif r >= 0.4: sev = "MODERATE"
    elif r >= 0.2: sev = "HEAVY"
    else: sev = "SEVERE"
    return round(r, 2), sev

def normalize_flow(location, payload, collected_at):
    """TomTom flowSegmentData -> list of reading dicts. Returns [] when the payload has no usable data."""
    d = (payload or {}).get("flowSegmentData")
    if not d:
        return []
    base = dict(module="traffic", location_id=location["id"], lat=location["lat"], lon=location["lon"],
                source="TomTom Traffic Flow (Flow Segment Data)",
                source_url="https://developer.tomtom.com/traffic-api/documentation/traffic-flow/flow-segment-data",
                observed_at=None,  # the flow response carries no observation time; we do not invent one
                collected_at=iso(collected_at), status="LIVE",
                completeness=d.get("confidence"),
                coverage="Nearest road segment to the point (not the whole neighbourhood)")
    ratio, sev = congestion_level(d.get("currentSpeed"), d.get("freeFlowSpeed"))
    rows = [
        {**base, "metric": "current_speed", "value": d.get("currentSpeed"), "unit": "km/h"},
        {**base, "metric": "free_flow_speed", "value": d.get("freeFlowSpeed"), "unit": "km/h"},
        {**base, "metric": "current_travel_time", "value": d.get("currentTravelTime"), "unit": "s"},
        {**base, "metric": "free_flow_travel_time", "value": d.get("freeFlowTravelTime"), "unit": "s"},
        {**base, "metric": "speed_ratio", "value": ratio, "unit": "ratio", "value_text": sev},
        {**base, "metric": "road_closure", "value": 1.0 if d.get("roadClosure") else 0.0, "unit": "bool"},
    ]
    if d.get("currentTravelTime") is not None and d.get("freeFlowTravelTime") is not None:
        rows.append({**base, "metric": "delay", "unit": "s",
                     "value": max(0, d["currentTravelTime"] - d["freeFlowTravelTime"])})
    return rows

def normalize_incidents(payload, collected_at):
    out = []
    for inc in (payload or {}).get("incidents", []) or []:
        p = inc.get("properties", {}) or {}
        geom = inc.get("geometry", {}) or {}
        coords = geom.get("coordinates")
        pt = None
        if geom.get("type") == "Point" and coords:
            pt = coords
        elif geom.get("type") == "LineString" and coords:
            pt = coords[0]
        events = p.get("events") or [{}]
        out.append(dict(
            source_id=p.get("id") or inc.get("id"),
            lon=pt[0] if pt else None, lat=pt[1] if pt else None,
            category=str(p.get("iconCategory")), magnitude=str(p.get("magnitudeOfDelay")),
            description=events[0].get("description"),
            road=", ".join(p.get("roadNumbers") or []) or None,
            from_text=p.get("from"), to_text=p.get("to"),
            delay_s=p.get("delay"), length_m=p.get("length"),
            start_time=p.get("startTime"), end_time=p.get("endTime"),
            collected_at=iso(collected_at)))
    return out

def unavailable(module, metric, location_id, reason, source):
    return dict(module=module, metric=metric, location_id=location_id, value=None, value_text=reason,
                unit=None, source=source, source_url=None, observed_at=None,
                collected_at=iso(now_ist()), status="UNAVAILABLE", completeness=0.0, coverage=None)

def is_active(notice, now=None):
    now = now or now_ist()
    s, e = parse_ts(notice.get("start_time")), parse_ts(notice.get("end_time"))
    return bool(s and e and s <= now <= e)

def is_upcoming(notice, hours=48, now=None):
    now = now or now_ist()
    s = parse_ts(notice.get("start_time"))
    return bool(s and now < s <= now + timedelta(hours=hours))
