"""BWSSB: no live flow/pressure/quality/interruption feed found. Provides
 (1) pumping-station locations from the OpenCity KML (static, HISTORICAL),
 (2) human-entered official notices (water interruptions, reservoir levels) with source URLs.
The KML is uploaded from the admin panel (or placed at data/water/pumping_stations.kml)."""
import os
from defusedxml import ElementTree as ET   # blocks XML entity-expansion attacks
import db
from data_normalizer import now_ist, is_active, is_upcoming, iso

KML_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "water", "pumping_stations.kml")
_cache = {"mtime": None, "stations": []}

def parse_kml(data):
    """bytes or str -> list of {name, lat, lon}. Raises ValueError if it is not usable KML."""
    try:
        root = ET.fromstring(data)
    except Exception as e:
        raise ValueError(f"not valid XML/KML ({type(e).__name__})")
    out = []
    for pm in root.iter():
        if not pm.tag.endswith("Placemark"):
            continue
        name, coords = None, None
        for ch in pm.iter():
            if ch.tag.endswith("name") and name is None:
                name = (ch.text or "").strip()
            if ch.tag.endswith("coordinates") and ch.text and coords is None:
                first = ch.text.strip().split()
                if first:
                    coords = first[0].split(",")
        if coords and len(coords) >= 2:
            try:
                out.append({"name": name or "Pumping station", "lon": float(coords[0]), "lat": float(coords[1])})
            except ValueError:
                continue
    if not out:
        raise ValueError("no placemarks with coordinates found")
    return out

def pumping_stations():
    if not os.path.exists(KML_PATH):
        return []
    m = os.path.getmtime(KML_PATH)
    if _cache["mtime"] == m:
        return _cache["stations"]
    try:
        with open(KML_PATH, "rb") as f:
            out = parse_kml(f.read())
    except (ValueError, OSError):
        out = []
    _cache.update(mtime=m, stations=out)
    return out

def summary():
    with db.conn() as c:
        notices = [dict(r) for r in c.execute(
            "SELECT * FROM notices WHERE module='water' ORDER BY COALESCE(start_time, notice_date) DESC LIMIT 200")]
    for n in notices:
        n["phase"] = "active" if is_active(n) else ("upcoming" if is_upcoming(n) else "past/other")
        n["status"] = "SCHEDULED" if n["phase"] != "past/other" else "HISTORICAL"
    st = pumping_stations()
    return {
        "pumping_stations": {"status": "HISTORICAL" if st else "UNAVAILABLE", "count": len(st), "items": st,
            "note": "Locations only. No operating status is available."},
        "interruptions": [n for n in notices if n["kind"] == "water_interruption"],
        "reservoir_levels": [n for n in notices if n["kind"] == "reservoir_level"],
        "supply_schedule": {"status": "UNAVAILABLE", "reason": "No machine-readable BWSSB schedule feed found."},
        "flow": {"status": "UNAVAILABLE", "reason": "No public flow telemetry."},
        "quality": {"status": "UNAVAILABLE",
            "reason": "No public water-quality readings. Quality is not the same as availability."},
        "generated_at": iso(now_ist()),
    }
