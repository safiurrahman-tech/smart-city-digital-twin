import sqlite3
from contextlib import contextmanager
import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS readings(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  module TEXT NOT NULL, metric TEXT NOT NULL, location_id TEXT,
  lat REAL, lon REAL, value REAL, value_text TEXT, unit TEXT,
  source TEXT NOT NULL, source_url TEXT,
  observed_at TEXT,            -- NULL when the source gives no observation time
  collected_at TEXT NOT NULL,
  status TEXT NOT NULL,        -- LIVE / DELAYED / HISTORICAL / SIMULATED / UNAVAILABLE
  completeness REAL,           -- 0..1
  coverage TEXT                -- what geography the reading actually represents
);
CREATE INDEX IF NOT EXISTS ix_read ON readings(module, metric, location_id, collected_at);
CREATE TABLE IF NOT EXISTS incidents(
  id INTEGER PRIMARY KEY AUTOINCREMENT, source_id TEXT, lat REAL, lon REAL,
  category TEXT, magnitude TEXT, description TEXT, road TEXT, from_text TEXT, to_text TEXT,
  delay_s INTEGER, length_m REAL, start_time TEXT, end_time TEXT, collected_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS matched_segments(
  location_id TEXT PRIMARY KEY,
  lat REAL NOT NULL, lon REAL NOT NULL,
  frc TEXT, coordinates_json TEXT NOT NULL,
  collected_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS notices(   -- human-entered from OFFICIAL notices (BESCOM / BWSSB / KSNDMC)
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  module TEXT NOT NULL,               -- electricity | water
  kind TEXT NOT NULL,                 -- planned_outage | water_interruption | reservoir_level | other
  title TEXT, area_text TEXT NOT NULL, location_id TEXT, lat REAL, lon REAL, radius_km REAL,
  start_time TEXT, end_time TEXT, value REAL, unit TEXT,
  source_name TEXT NOT NULL, source_url TEXT NOT NULL, notice_date TEXT,
  entered_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS location_overrides(
  location_id TEXT PRIMARY KEY, lat REAL NOT NULL, lon REAL NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS admin_audit(
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, action TEXT NOT NULL, detail TEXT, ip TEXT
);
CREATE TABLE IF NOT EXISTS api_usage(api TEXT, period TEXT, count INTEGER, PRIMARY KEY(api, period));
CREATE TABLE IF NOT EXISTS collector_log(
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, job TEXT, ok INTEGER, message TEXT
);
"""

@contextmanager
def conn():
    c = sqlite3.connect(config.DB_PATH)
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally:
        c.close()

def init():
    with conn() as c:
        c.executescript(SCHEMA)
