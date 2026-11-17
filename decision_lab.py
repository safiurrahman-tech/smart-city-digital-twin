"""CitySync Decision Lab — deterministic, EXPLICITLY hypothetical impact simulator.

Traffic measurements are from already-saved TomTom records. No TomTom requests are made
here. Extra delay estimates are an invented teaching assumption, not a learned or
calibrated traffic or power-system model. Never label this output a prediction.
"""
from math import isfinite
from typing import Any

import config
import db
from data_normalizer import freshness, now_ist, iso
from locations import BY_ID

# Example-only assumptions: not operational thresholds or empirical coefficients.
OVERLOAD_AT_PERCENT = 100.0
LOAD_REDUCTION_POINTS = 20.0
ADDED_DELAY_PER_OUTAGE_MINUTE_SECONDS = 9.0
MAX_ADDED_DELAY_SECONDS = 1200.0


class ValidationError(ValueError):
    pass


class NoTrafficData(Exception):
    pass


def _numeric(value: Any, label: str, lower: float, upper: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError(f"{label} must be a number between {lower:g} and {upper:g}")
    try:
        number = float(value)
    except (OverflowError, ValueError):
        raise ValidationError(f"{label} must be a finite number") from None
    if not isfinite(number):
        raise ValidationError(f"{label} must be a finite number")
    if not lower <= number <= upper:
        raise ValidationError(f"{label} must be between {lower:g} and {upper:g}")
    return number


def _boolean(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValidationError(f"{label} must be true or false")
    return value


def _snapshot(location_id: str) -> dict:
    """Return a single coherent *collected_at* snapshot for the specified nearest road segment."""
    with db.conn() as c:
        stamp = c.execute(
            "SELECT collected_at FROM readings WHERE module='traffic' AND location_id=? "
            "AND lat=? AND lon=? AND metric='current_travel_time' ORDER BY collected_at DESC, id DESC LIMIT 1",
            (location_id, BY_ID[location_id]["lat"], BY_ID[location_id]["lon"]),
        ).fetchone()
        if stamp is None:
            raise NoTrafficData("No saved TomTom traffic snapshot for this location yet. Start the collector first.")
        rows = c.execute(
            "SELECT * FROM readings WHERE module='traffic' AND location_id=? AND lat=? AND lon=? "
            "AND collected_at=? ORDER BY id DESC",
            (location_id, BY_ID[location_id]["lat"], BY_ID[location_id]["lon"], stamp["collected_at"]),
        ).fetchall()
    measures = {}
    for row in rows:
        measures.setdefault(row["metric"], dict(row))
    current = measures.get("current_travel_time", {}).get("value")
    free = measures.get("free_flow_travel_time", {}).get("value")
    if current is None or free is None or current < 0 or free < 0:
        raise NoTrafficData("Latest traffic snapshot lacks valid current and free-flow travel times")
    status, age = freshness("LIVE", stamp["collected_at"], config.FLOW_INTERVAL_MIN)
    speed_ratio = measures.get("speed_ratio", {}).get("value")
    delay = max(0.0, float(current) - float(free))
    return {
        "current_travel_time_s": round(float(current), 1),
        "free_flow_travel_time_s": round(float(free), 1),
        "measured_delay_s": round(delay, 1),
        "current_speed_kmh": measures.get("current_speed", {}).get("value"),
        "free_flow_speed_kmh": measures.get("free_flow_speed", {}).get("value"),
        "speed_ratio": speed_ratio,
        "source_confidence": measures.get("current_travel_time", {}).get("completeness"),
        "collected_at": stamp["collected_at"],
        "age_seconds": age,
        "status": status,
        "source": "TomTom Traffic Flow, locally collected snapshot",
        "coverage": "Nearest mapped road segment only; not the whole neighbourhood",
        "observed_at": None,
    }


def _outcome(load: float, duration_minutes: float, backup: bool, forced_outage: bool,
             source: dict) -> dict:
    outage = forced_outage or load >= OVERLOAD_AT_PERCENT
    signals_online = (not outage) or backup
    # Pressure modifier is also hypothetical: >0 when measured speed falls below free flow.
    ratio = source.get("speed_ratio")
    pressure = max(0.0, min(1.0, 1.0 - ratio)) if isinstance(ratio, (float, int)) else 0.0
    added = 0.0 if signals_online else min(
        MAX_ADDED_DELAY_SECONDS,
        round(ADDED_DELAY_PER_OUTAGE_MINUTE_SECONDS * duration_minutes * (1 + pressure), 1)
    )
    return {
        "effective_load_percent": round(load, 1),
        "modeled_grid_outage": outage,
        "signals_online": signals_online,
        "hypothetical_added_delay_s": added,
        "modeled_travel_time_s": round(source["current_travel_time_s"] + added, 1),
        "modeled_total_delay_s": round(source["measured_delay_s"] + added, 1),
    }


def simulate(payload: dict, source_override: dict | None = None) -> dict:
    """Compare no-action and selected-action outcomes from same saved TomTom baseline."""
    if not isinstance(payload, dict):
        raise ValidationError("JSON object required")
    allowed = {"location_id", "load_percent", "outage_minutes", "backup_power", "load_reduction", "forced_outage"}
    unknown = set(payload) - allowed
    if unknown:
        raise ValidationError("Unknown input keys: " + ", ".join(sorted(unknown)))
    location_id = payload.get("location_id", "silk_board")
    if not isinstance(location_id, str) or location_id not in BY_ID:
        raise ValidationError("location_id must be one of the configured monitoring locations")
    load = _numeric(payload.get("load_percent", 105), "load_percent", 50, 120)
    minutes = _numeric(payload.get("outage_minutes", 20), "outage_minutes", 5, 120)
    backup = _boolean(payload.get("backup_power", False), "backup_power")
    reduction = _boolean(payload.get("load_reduction", False), "load_reduction")
    forced = _boolean(payload.get("forced_outage", False), "forced_outage")
    source = source_override if source_override is not None else _snapshot(location_id)
    baseline = _outcome(load, minutes, False, forced, source)
    action_load = max(0, load - (LOAD_REDUCTION_POINTS if reduction else 0))
    with_action = _outcome(action_load, minutes, backup, forced, source)
    avoided = round(baseline["hypothetical_added_delay_s"] - with_action["hypothetical_added_delay_s"], 1)
    if forced:
        recommendation = "The forced outage cannot be prevented by reducing load in this toy model. Try backup power."
    elif load >= OVERLOAD_AT_PERCENT and reduction and with_action["signals_online"]:
        recommendation = "Selected load reduction avoids the *modeled* overload threshold. This is not a verified grid intervention."
    elif baseline["modeled_grid_outage"] and not with_action["signals_online"]:
        recommendation = "Signals are offline in the toy model. Try backup power or a load reduction that goes below 100%."
    elif baseline["modeled_grid_outage"] and backup:
        recommendation = "Selected backup keeps the signals running in the model despite the assumed grid outage."
    else:
        recommendation = "No simulated signal disruption at these inputs."
    return {
        "type": "SIMULATED_DECISION_SCENARIO",
        "baseline_origin": "ILLUSTRATIVE_DEMO" if source_override is not None else "TOMTOM_SNAPSHOT",
        "generated_at": iso(now_ist()),
        "location": BY_ID[location_id],
        "real_traffic_baseline": source,
        "inputs": {
            "location_id": location_id,
            "load_percent": load,
            "outage_minutes": minutes,
            "backup_power": backup,
            "load_reduction": reduction,
            "forced_outage": forced,
        },
        "without_action": baseline,
        "with_action": with_action,
        "hypothetical_delay_avoided_s": avoided,
        "recommendation": recommendation,
        "assumptions": {
            "grid_overload_threshold_percent": OVERLOAD_AT_PERCENT,
            "load_reduction_points": LOAD_REDUCTION_POINTS,
            "added_delay_seconds_per_outage_minute": ADDED_DELAY_PER_OUTAGE_MINUTE_SECONDS,
            "pressure_modifier": "1 + max(0, min(1, 1 - TomTom speed ratio))",
            "max_added_delay_seconds": MAX_ADDED_DELAY_SECONDS,
            "signal_backup": "If enabled, traffic signals remain online during modeled outage",
            "forced_outage": "Overrides load threshold and is unaffected by demand reduction",
        },
        "limitations": [
            "The saved TomTom travel time represents the selected nearest road segment, not an intersection-wide delay.",
            "Power load and outage are user-entered hypothetical inputs; no BESCOM grid telemetry is connected.",
            "Extra traffic delay is based on transparent invented coefficients, not a validated traffic model.",
            "Scenario output is NOT a forecast, measured avoided delay or evidence of physical causation.",
            "Old TomTom records are labeled DELAYED and are not presented as live readings.",
        ],
    }


def simulate_demo(payload: dict) -> dict:
    """Explicit hypothetical baseline for offline jury demos; never represent as TomTom LIVE."""
    demo_source = {
        "current_travel_time_s": 520, "free_flow_travel_time_s": 400,
        "measured_delay_s": 120, "current_speed_kmh": 28,
        "free_flow_speed_kmh": 35, "speed_ratio": 0.8,
        "source_confidence": None, "collected_at": None,
        "age_seconds": None, "status": "SIMULATED",
        "source": "CitySync illustrative demo fixture (not TomTom data)",
        "coverage": "Fictional teaching example, not a real road segment measurement",
        "observed_at": None,
    }
    result = simulate(payload, source_override=demo_source)
    result["limitations"].insert(0, "The baseline is fictional demo data. It must never be labeled LIVE or observed.")
    return result
