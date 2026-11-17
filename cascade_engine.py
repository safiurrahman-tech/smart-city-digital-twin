"""Illustrative cross-utility dependency model. NOT verified BESCOM/BWSSB telemetry.

Assumes an example water pump loses utility power during the same modeled outage
unless pump backup is enabled. An example storage buffer determines exposure,
not a real measured water interruption. No claim of real physical service impact.
"""
import math

class CascadeValidationError(ValueError):
    pass


def _boolean(data, key):
    value = data.get(key)
    if not isinstance(value, bool):
        raise CascadeValidationError(f'{key} must be true or false')
    return value


def _number(data, key, low, high):
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
        raise CascadeValidationError(f'{key} must be a finite number between {low} and {high}')
    return float(value)


def _stage(grid_off, minutes, buffer, backup):
    pump_running = not grid_off or backup
    uncovered = round(max(0.0, minutes-buffer), 1) if not pump_running else 0.0
    return {'grid_outage':grid_off,'pump_running':pump_running,
            'service_at_risk':uncovered>0,'illustrative_unbuffered_minutes':uncovered,
            'interpretation':('No pump interruption under the configured assumptions' if pump_running
                              else 'Assumed storage capacity covers outage duration' if uncovered == 0
                              else 'Modeled storage exhausted: illustrative water service at risk')}


def simulate(payload):
    if not isinstance(payload,dict):raise CascadeValidationError('JSON object required')
    allowed={'grid_outage_without','grid_outage_with','outage_minutes','pump_backup','buffer_minutes'}
    if set(payload)-allowed:raise CascadeValidationError('Unknown input field')
    before=_boolean(payload,'grid_outage_without');after=_boolean(payload,'grid_outage_with')
    backup=_boolean(payload,'pump_backup');minutes=_number(payload,'outage_minutes',5,120)
    buffer=_number(payload,'buffer_minutes',0,120)
    baseline=_stage(before,minutes,buffer,False)
    action=_stage(after,minutes,buffer,backup)
    return {'type':'HYPOTHETICAL_WATER_PUMP_CASCADE','without_action':baseline,'with_action':action,
            'assumptions':{'pump_dependency':'Example pump depends on same grid zone as modeled traffic signal',
                           'backup':'When enabled, hypothetical local backup powers pump during outage',
                           'storage_buffer_minutes':buffer,
                           'what_this_is_not':'Not measured pressure, water demand, pump condition, or confirmed service interruption'},
            'modelled_at_risk_minutes_avoided':round(max(0,baseline['illustrative_unbuffered_minutes']-action['illustrative_unbuffered_minutes']),1),
            'disclaimer':'All pumping outcomes are hypothetical teaching assumptions. Not BWSSB telemetry or validated forecasts.'}
