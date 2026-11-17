import os
from dotenv import load_dotenv
load_dotenv()

TZ = "Asia/Kolkata"
TOMTOM_API_KEY = os.getenv("TOMTOM_API_KEY", "")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")
DB_PATH = os.getenv("DB_PATH", "citysync.db")
FLOW_INTERVAL_MIN = int(os.getenv("FLOW_INTERVAL_MIN", "15"))
INCIDENT_INTERVAL_MIN = int(os.getenv("INCIDENT_INTERVAL_MIN", "30"))
FLOW_MONTHLY_BUDGET = int(os.getenv("TOMTOM_FLOW_MONTHLY_BUDGET", "20000"))
INCIDENT_MONTHLY_BUDGET = int(os.getenv("TOMTOM_INCIDENT_MONTHLY_BUDGET", "2500"))
# A reading older than STALE_FACTOR x its polling interval is shown as DELAYED.
STALE_FACTOR = 2
# City-wide bounding box for ONE incident call: minLon,minLat,maxLon,maxLat (approximate Bengaluru extent)
CITY_BBOX = (77.45, 12.80, 77.80, 13.15)

# --- Admin login (v2) ---
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")            # simple option: plain password (min 10 chars)
ADMIN_PASSWORD_HASH = os.getenv("ADMIN_PASSWORD_HASH", "")  # better option: python -m scripts.make_password_hash
SECRET_KEY = os.getenv("SECRET_KEY", "")                    # signs the session cookie
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "0") == "1"      # set 1 when served over HTTPS
if ADMIN_TOKEN in ("", "change-me"):
    ADMIN_TOKEN = ""   # placeholder values never count as a credential
