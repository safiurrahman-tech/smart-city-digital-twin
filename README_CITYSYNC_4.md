# CitySync 4.0 — Automatic Intelligence & Security Operations upgrade

This **builds on the uploaded CitySync 3.1.4 Auto Economics** project. It retains all original Flask/React/Leaflet/SQLite/TomTom/digital-twin modules and adds a working **automatic operations dashboard, risk-ranked Bengaluru areas, three evidence-aware graph panels, persisted/deduplicated alerts, opt-in browser alarms, authorized acknowledgement, and logged unauthorized access attempts**.

## Windows installation

1. Extract the ZIP and open the inner `CitySync_4_0_Command_Center` folder (the directory with `app.py`).
2. PowerShell: ` .\\SETUP_WINDOWS.bat ` (the leading ` .\\ ` is required).
3. `notepad .env` and set `TOMTOM_API_KEY`, `ADMIN_PASSWORD`, `SECRET_KEY`. Never send these to chat or commit `.env`.
4. If admin password is repeatedly wrong: stop the server, run ` .\\RESET_ADMIN_WINDOWS.bat `, then restart. A leftover `ADMIN_PASSWORD_HASH` takes precedence over `ADMIN_PASSWORD` until reset.
5. ` .\\START_WINDOWS.bat ` and visit `http://127.0.0.1:5000/operations`.
6. The legacy integrated digital twin remains at `/`, admin at `/admin`, and health at `/api/health`.
7. Click **Enable alarm** in `/operations` for sound on *new* high advisories. The browser page must remain open and audio permission may be required.

## Key files

- `v4_intelligence.py`: automatic risk ranking and explicit absence of utility telemetry.
- `v4_security.py`: persisted alerts, acknowledgements and denied-access audit.
- `v4_api.py`: source-aware operations and security REST endpoints.
- `static/operations.html`, `.css`, `.js`: responsive command center and charts.
- `static/v4_banner.js`: compact persistent priority banner on the original home page.
- `tests/test_v4_intelligence.py`: offline AI-screening regression tests.
- `docs/CITYSYNC_4_ARCHITECTURE.md`: source boundaries and technical architecture.
- `docs/CITYSYNC_4_JURY_SCRIPT.md`: safe end-to-end presentation.

## Feature honesty

- Automatic area screening: **implemented** using Open-Meteo and fresh TomTom readings when available; no manual input required.
- Traffic forecast: **experimental**, withheld until at least 12 historical samples spanning 60 minutes are available; its basis is linear extrapolation, not validated forecasting.
- Electricity prediction: **NOT IMPLEMENTED** without a verified load dataset; the panel visibly states unavailable.
- Water infrastructure damage prediction: **NOT IMPLEMENTED** without sensors / pipe maintenance records; rainfall vulnerability screening is heuristic.
- Security-event logging: **implemented** for failed protected API requests; no validated cyber-threat ML classifier.
- Alarm: **opt-in browser audio on new unacknowledged HIGH events**; not SMS/WhatsApp or background notification.

## Evaluation and next integrations

The project includes `requirements.txt`, original Python tests and JS tests, plus offline V4 tests. To progress toward actual reliable forecasting, acquire authorized BESCOM feeder histories, BWSSB pipe/chamber sensor data and incident labels; train/validate with chronological holdouts before displaying quantitative forecast accuracy.
