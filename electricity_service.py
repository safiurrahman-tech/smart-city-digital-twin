"""BESCOM: no documented public outage API was found. This module serves ONLY notices that a human
copied from official BESCOM channels (website / Mithra / 1912 announcements), with source URL.
Unplanned outages are always reported UNAVAILABLE. Nothing here is LIVE telemetry."""
import config, db
from data_normalizer import now_ist, is_active, is_upcoming, iso

def summary():
    with db.conn() as c:
        rows = [dict(r) for r in c.execute(
            "SELECT * FROM notices WHERE module='electricity' ORDER BY start_time DESC LIMIT 200")]
    for r in rows:
        r["status"] = "SCHEDULED" if (is_active(r) or is_upcoming(r)) else "HISTORICAL"
        r["phase"] = "active" if is_active(r) else ("upcoming" if is_upcoming(r) else "past/other")
        r["restoration_time"] = r["end_time"]  # planned end time; NOT a confirmed restoration time
    return {
        "planned_notices": rows,
        "unplanned_outages": {"status": "UNAVAILABLE",
            "reason": "No public BESCOM feed for unplanned outages was found. Use BESCOM Mithra or 1912."},
        "demand": {"status": "UNAVAILABLE",
            "reason": "No public real-time grid load/demand feed verified. OpenCity has annual statistics only."},
        "generated_at": iso(now_ist()),
    }
