"""Scheduler: source-specific intervals, Asia/Kolkata, never overlapping runs."""
import logging
from apscheduler.schedulers.background import BackgroundScheduler
import config, db, traffic_service
from locations import get_locations
from data_normalizer import iso, now_ist

log = logging.getLogger("collector")

def _log(job, ok, msg):
    with db.conn() as c:
        c.execute("INSERT INTO collector_log(ts,job,ok,message) VALUES(?,?,?,?)", (iso(now_ist()), job, int(ok), str(msg)[:500]))

def run_flow():
    res = traffic_service.collect_flow(get_locations())
    _log("flow", all(v == "ok" for v in res.values()), res)

def run_incidents():
    msg = traffic_service.collect_incidents()
    _log("incidents", msg.startswith("ok"), msg)

def run_ai():
    """Refresh risk triage without depending on anyone opening a dashboard."""
    try:
        import v4_intelligence
        report=v4_intelligence.evaluate_and_store()
        _log('auto_ai',True,f"Evaluated {len(report['zones'])} zones, {len(report['alerts'])} active alerts; weather {report['weather_status']}")
    except Exception as exc:
        log.exception('Automatic early warning job failed')
        _log('auto_ai',False,type(exc).__name__)


def start():
    s = BackgroundScheduler(timezone=config.TZ, job_defaults={"max_instances": 1, "coalesce": True})
    s.add_job(run_flow, "interval", minutes=config.FLOW_INTERVAL_MIN, id="flow", next_run_time=now_ist())
    s.add_job(run_incidents, "interval", minutes=config.INCIDENT_INTERVAL_MIN, id="incidents", next_run_time=now_ist())
    s.add_job(run_ai, 'interval', minutes=10, id='auto_ai', next_run_time=now_ist())
    s.start()
    return s
