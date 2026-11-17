"""Tamper-aware local admin-security event and alert tracking.
The app never accepts a client-provided severity/actor as trusted evidence.
"""
from datetime import datetime, timedelta, timezone
from flask import request
import db
from data_normalizer import iso, now_ist


def init():
    with db.conn() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS v4_alerts (
            alert_key TEXT PRIMARY KEY, kind TEXT NOT NULL, severity TEXT NOT NULL,
            title TEXT NOT NULL, location_id TEXT, detail TEXT NOT NULL,
            source TEXT NOT NULL, first_seen TEXT NOT NULL, last_seen TEXT NOT NULL,
            acknowledged_at TEXT, acknowledged_by TEXT, currently_active INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS v4_security_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL,
            path TEXT NOT NULL, method TEXT NOT NULL, status_code INTEGER NOT NULL,
            source_ip TEXT, category TEXT NOT NULL, severity TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS ix_v4_sec_ts ON v4_security_events(ts);
        ''')


def reconcile(alerts):
    """Remember alerts by stable keys; reset acknowledgement only after an event resolves."""
    stamp=iso(now_ist())
    keys={a['key'] for a in alerts}
    with db.conn() as c:
        previous=[dict(r) for r in c.execute('SELECT alert_key FROM v4_alerts WHERE currently_active=1')]
        for p in previous:
            if p['alert_key'] not in keys:
                c.execute('UPDATE v4_alerts SET currently_active=0 WHERE alert_key=?',(p['alert_key'],))
        for a in alerts:
            c.execute('''INSERT INTO v4_alerts(alert_key,kind,severity,title,location_id,detail,source,first_seen,last_seen,currently_active)
               VALUES (?,?,?,?,?,?,?,?,?,1)
               ON CONFLICT(alert_key) DO UPDATE SET kind=excluded.kind,severity=excluded.severity,
               title=excluded.title,detail=excluded.detail,source=excluded.source,
               last_seen=excluded.last_seen,currently_active=1,
               acknowledged_at=CASE WHEN v4_alerts.currently_active=0 THEN NULL ELSE v4_alerts.acknowledged_at END,
               acknowledged_by=CASE WHEN v4_alerts.currently_active=0 THEN NULL ELSE v4_alerts.acknowledged_by END''',
                (a['key'],a['kind'],a['severity'],a['title'],a.get('location_id'),
                 a['detail'],a['source'],stamp,stamp))


def alerts():
    with db.conn() as c:
        return [dict(r) for r in c.execute('SELECT * FROM v4_alerts WHERE currently_active=1 ORDER BY CASE severity WHEN "CRITICAL" THEN 0 WHEN "HIGH" THEN 1 ELSE 2 END, first_seen DESC')]


def acknowledge(key):
    stamp=iso(now_ist())
    with db.conn() as c:
        n=c.execute('UPDATE v4_alerts SET acknowledged_at=?,acknowledged_by=? WHERE alert_key=? AND currently_active=1',
                    (stamp,'local_admin',key)).rowcount
    return bool(n)


def log_denial():
    """Log only denied accesses to protected API paths, not ordinary page views."""
    ip=(request.remote_addr or '')[:64]
    now=iso(now_ist()); path=request.path[:240]
    category='UNAUTHORIZED_ALERT_CHANGE' if path.startswith('/api/v4/alerts/') else 'UNAUTHORIZED_ADMIN_ACCESS'
    with db.conn() as c:
        c.execute('INSERT INTO v4_security_events(ts,path,method,status_code,source_ip,category,severity) VALUES(?,?,?,?,?,?,?)',
                  (now,path,request.method,request.environ.get('v4_denial_status',403),ip,category,'WATCH'))


def security_signal():
    """Public *aggregate* for dashboard alarms; never exposes raw IPs or paths."""
    since=(now_ist()-timedelta(hours=1)).isoformat()
    with db.conn() as c:
        count=c.execute('SELECT COUNT(*) AS n FROM v4_security_events WHERE ts>=?',(since,)).fetchone()['n']
    return {'severity':'HIGH' if count>=5 else ('WATCH' if count else 'NORMAL'),
            'denied_last_hour':count,'kind':'ACCESS_DENIAL_RATE',
            'note':'Multiple denied sensitive API requests; investigate. Not proof of an intrusion.'}


def security_summary():
    since=(now_ist()-timedelta(hours=24)).isoformat()
    with db.conn() as c:
        events=[dict(x) for x in c.execute('SELECT * FROM v4_security_events WHERE ts>=? ORDER BY id DESC LIMIT 100',(since,))]
        total=c.execute('SELECT COUNT(*) AS n FROM v4_security_events WHERE ts>=?',(since,)).fetchone()['n']
    return {'status':'WATCH' if total>=5 else ('INFO' if total else 'NORMAL'),
            'denied_access_24h':total,'events':events,
            'note':'Evidence-based server-denied sensitive API requests only. Counts are not proof of intrusion.'}
