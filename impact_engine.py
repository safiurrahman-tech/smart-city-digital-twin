"""Rule-based cross-system impact engine. Every output is a HYPOTHESIS, never a measured fact.
A rule fires only when the inputs it needs actually exist; otherwise it reports insufficient data.
Co-location is not causation: these are prompts for a human operator."""
import db, water_service
from locations import get_locations
from geo import km
from data_normalizer import now_ist, is_active, iso, freshness
import config

def _notice_covers(n, loc):
    if n.get("location_id") == loc["id"]:
        return True
    if n.get("lat") is not None and n.get("lon") is not None and n.get("radius_km"):
        return km(n["lat"], n["lon"], loc["lat"], loc["lon"]) <= n["radius_km"]
    return False

def _latest_traffic(loc_id):
    with db.conn() as c:
        r = c.execute("SELECT value, value_text, collected_at FROM readings WHERE module='traffic' AND "
                      "metric='speed_ratio' AND location_id=? ORDER BY collected_at DESC LIMIT 1", (loc_id,)).fetchone()
    if not r:
        return None
    status, _ = freshness("LIVE", r["collected_at"], config.FLOW_INTERVAL_MIN)
    return {"ratio": r["value"], "severity": r["value_text"], "status": status, "collected_at": r["collected_at"]}

def evaluate(pump_radius_km=3.0):
    now = now_ist()
    with db.conn() as c:
        notices = [dict(r) for r in c.execute("SELECT * FROM notices")]
    stations = water_service.pumping_stations()
    warnings, skipped = [], []
    if not stations:
        skipped.append("R1 needs the BWSSB pumping-station KML (data/water/pumping_stations.kml); not loaded.")
    for loc in get_locations():
        t = _latest_traffic(loc["id"])
        outages = [n for n in notices if n["module"] == "electricity" and n["kind"] == "planned_outage"
                   and is_active(n, now) and _notice_covers(n, loc)]
        wints = [n for n in notices if n["module"] == "water" and n["kind"] == "water_interruption"
                 and is_active(n, now) and _notice_covers(n, loc)]
        for n in outages:
            near = [s for s in stations if km(s["lat"], s["lon"], loc["lat"], loc["lon"]) <= pump_radius_km]
            if near:  # R1
                warnings.append(dict(rule="R1_outage_near_pumping", level="WATCH", kind="HYPOTHESIS",
                    location=loc["id"], message=f"Planned power outage active near {loc['name']}; "
                    f"{len(near)} BWSSB pumping station(s) within {pump_radius_km} km. Pumping MAY be affected "
                    "if those stations draw from the affected feeder (feeder mapping unknown).",
                    evidence=[f"notice #{n['id']}: {n['source_name']}"] + [s["name"] for s in near[:3]]))
            if t and t["severity"] in ("HEAVY", "SEVERE") and t["status"] == "LIVE":  # R2
                warnings.append(dict(rule="R2_outage_plus_congestion", level="WATCH", kind="HYPOTHESIS",
                    location=loc["id"], message=f"Active outage and {t['severity'].lower()} congestion at "
                    f"{loc['name']}: crew travel times MAY be longer than usual.",
                    evidence=[f"notice #{n['id']}", f"live speed ratio {t['ratio']} at {t['collected_at']}"]))
        for n in wints:  # R3
            if t and t["severity"] in ("MODERATE", "HEAVY", "SEVERE") and t["status"] == "LIVE":
                warnings.append(dict(rule="R3_water_interruption_traffic", level="INFO", kind="HYPOTHESIS",
                    location=loc["id"], message=f"Water interruption notice active at {loc['name']} with "
                    f"{t['severity'].lower()} traffic. Tanker movements could add to road load (no tanker data held).",
                    evidence=[f"notice #{n['id']}", f"speed ratio {t['ratio']}"]))
    return {"generated_at": iso(now), "label": "HYPOTHESES - not verified causal relationships",
            "warnings": warnings, "rules_not_evaluated": skipped}
