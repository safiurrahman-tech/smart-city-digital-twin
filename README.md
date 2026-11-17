# CitySync 4.0 (upgraded from uploaded CitySync 3.1.4)

**Start with [`README_CITYSYNC_4.md`](README_CITYSYNC_4.md)** for the new automatic operations, alert, graph and cybersecurity features. See [`docs/CITYSYNC_4_ARCHITECTURE.md`](docs/CITYSYNC_4_ARCHITECTURE.md) for verified source boundaries.

---

# CitySync 3.0 — AI-powered Smart City Digital Twin (hackathon prototype)

**Monitor → Connect → Predict → Simulate → Prevent**

An interactive, multi-infrastructure decision-support application for Bengaluru. This complete local prototype uses saved TomTom traffic observations when configured, optional Open-Meteo weather, source-linked utility notices, cross-system synthetic risk simulation, a synthetic-data RandomForest model, a virtual map, financial exposure comparisons, SQLite history, and secure administration.

**Important distinction:** Real measured traffic is never labeled as synthetic, and modeled road/flood/electricity/water/economic impacts are **not** claimed to be accurate forecasts or actual financial losses. This is not an operational municipal control system.

## Windows installation (open the INNER folder with `SETUP_WINDOWS.bat`)

Prerequisite: Windows 10/11, Python **3.11–3.13** installed with `py` launcher, internet for first package installation and online map/weather. **Python 3.13 is supported by recent NumPy/scikit-learn wheels.** On an older laptop, setup may be slower due to installing ML libraries.

1. Extract `CitySync_3_0_Digital_Twin_Complete.zip` and open the **`CitySync_3_0_Digital_Twin`** folder containing `app.py` in VS Code.
2. Open **Terminal → New Terminal**. Stop old CitySync servers on port `5000` with `Ctrl+C`.
3. Run `.\SETUP_WINDOWS.bat` (actual command: `.\SETUP_WINDOWS.bat`), then configure `.env`:

   ```powershell
   .\SETUP_WINDOWS.bat
   notepad .env
   ```

4. Add your own private credentials. **Do not post credentials in chat or commit `.env`.**

   ```dotenv
   TOMTOM_API_KEY=YOUR_REGENERATED_TOMTOM_KEY
   ADMIN_PASSWORD=YOUR_NEW_ADMIN_PASSWORD_AT_LEAST_10_CHARACTERS
   ADMIN_PASSWORD_HASH=
   SECRET_KEY=YOUR_RANDOM_SESSION_SECRET_AT_LEAST_24_CHARACTERS
   ```

5. Recommended: **instead of manually managing admin and session secrets**, run:

   ```powershell
   .\RESET_ADMIN_WINDOWS.bat
   ```

   It will generate a strong admin password (or accept yours), remove any stale `ADMIN_PASSWORD_HASH` that overrides your password, and create a session secret if missing. Record the generated password privately. Restart after running reset.

6. Start:

   ```powershell
   .\START_WINDOWS.bat
   ```

7. Open **http://127.0.0.1:5000/** (dashboard) and **http://127.0.0.1:5000/admin** (admin).

> **PowerShell tip:** You must include `.\` before `.bat` in the current folder. If script is not found, `dir` and `cd` into the folder with `SETUP_WINDOWS.bat`.

### Admin password repeatedly incorrect?

- **Fix:** stop the server (`Ctrl+C`), run `.\RESET_ADMIN_WINDOWS.bat`, save the generated private password and restart.
- If you have `ADMIN_PASSWORD_HASH` configured, it takes priority over `ADMIN_PASSWORD`. The reset tool clears the stale hash in `.env` and sets a new password.
- Environment variables inherited from an older terminal can override `.env`; open a fresh terminal if necessary. Do not expose or print secrets in screenshots.
- After **five** failed logins, the app locks the IP for **five minutes**. Resetting `.env` does not bypass a lockout in a running process; restart after updating the password.
- If an old server still occupies port 5000, your browser may be talking to the old project. Stop every other CitySync server first.

## Full feature coverage

| Workspace | Functional implementation | Data classification |
| --- | --- | --- |
| Overview | Road feed status, relative congestion, incidents, utility readiness, simulated city health after a run, dynamic revenue impact | Mixed, explicitly labeled |
| Traffic | Seven interactive Bengaluru points, nearest TomTom matched segments, source observations and historical trend, relative corridor screening | Real readings when configured; route screening is NOT turn-by-turn navigation |
| Electricity | No made-up live grid meters; admin-entered official power notices, demand-surge scenarios and modeled signal backup effect | Source-linked notices + synthetic |
| Water | Admin-uploaded pumping-station KML, BWSSB notices, modeled drainage, leakage, shortage and rain dependency | Source-linked notices + synthetic |
| Weather | Open-Meteo Bengaluru temperature/humidity/precipitation, reported hourly precipitation probability | Provider data when available; not flood telemetry |
| AI risk | 4 subsystem risk indices; RandomForest trained on **synthetic** generator only, withheld synthetic MAE; explanation + response suggestions | **Demo-only**, not field validated |
| Digital twin | Six scenario presets and editable rainfall/traffic/power/drainage/leak/duration variables, six interventions, affected zones on map, before-after | Explicit hypothetical effects |
| Economic impact | Estimated business revenue at risk, commuter time cost, intervention costs, net modeled exposure avoided; editable INR assumptions | **Synthetic estimates**, not measured losses |
| Alerts | Rule-labeled live traffic / sourced notices and separately labeled scenario risks | Clearly source-labeled |
| History | Saved scenario experiments with date/location filters and financial CSV export, real TomTom traffic history | SQLite data stored locally |
| Data provenance | Model caveats, source readiness, evidence boundaries | Transparent |
| Admin | Password login, session + CSRF, notice edit/delete, map-coordinate edits, KML upload, collector controls, audit | Local authenticated admin |

**Frontend:** locally bundled React (no npm build required) + professional custom responsive CSS + Leaflet/OpenStreetMap with SVG map fallback. **Backend:** Flask, Waitress. **Analytics:** NumPy, scikit-learn RandomForest on synthetic scenarios; Pandas available for future dataset integration. **Database:** SQLite for portable offline demos. Tailwind, MySQL and Firebase are **not required or implemented** in this local hackathon build.

## Jury demonstration in 90 seconds

1. **Monitor:** Open Overview, show TomTom feed count and source flags. If TomTom is not configured, note `UNAVAILABLE` rather than presenting fake traffic.
2. **Connect:** Open the Digital Twin lab and select **Heavy monsoon rain** at Silk Board or Whitefield.
3. **Predict (synthetic):** Show rainfall, assumed water level, drainage capacity, and resulting flood/road risk indices.
4. **Simulate:** Run once with no actions; observe the impacted zones and risk scores. Enable **Drain clearing** and **Traffic diversion**, then run again.
5. **Prevent:** Compare before/after synthetic health, congestion, alerts and recommended interventions.
6. **Economic impact:** Explain revenue-at-risk, commuter time burden, response cost and net exposure avoided **under stated illustrative assumptions**.
7. **Evidence:** Export CSV of locally saved experiments; open Admin for traceable official notices and collector health (avoid exposing `.env`).

Alternative scenarios: traffic surge, electricity demand spike, pipe leak, compound failure and normal conditions. All scenario controls work offline without a TomTom key, while clearly labeled **SYNTHETIC_DEMO_BASELINE**.

## Architecture, demo data, and test coverage

- [Diagram and technical architecture](docs/ARCHITECTURE.md) ([SVG](docs/architecture.svg)).
- [Demo script](docs/DEMO_SCRIPT.md).
- Demo inputs: `data/demo_synthetic_scenarios.csv` and monitored coordinates `data/bengaluru_monitoring_points.csv` (not measured city utility datasets).
- Automated tests:

  ```powershell
  .\.venv\Scripts\python.exe -m pytest -q tests
  ```

- Node test for legacy V6.1 decision helpers (optional, if Node installed): `node --test tests_js/test_decision_helpers.cjs`.
- Optional live TomTom connection check, **consumes API quota**: `.\.venv\Scripts\python.exe -m scripts.test_connections`.

## Security and reliability

Local-only default `127.0.0.1:5000`; don't expose directly to the internet. Never put secrets in source control. Admin auth uses a signed HTTP-only session cookie, CSRF protection on mutating admin endpoints, audit logging and a short rate-limited lockout. For real deployments add HTTPS, cloud identity, a production database, monitoring and independent security review. Review API use quotas before triggering manual collection.

## Important limitations

- TomTom nearest matched segments are **not** all roads or a city-wide congestion measurement.
- No verified continuous BESCOM, BWSSB or flooding telemetry is connected; source-backed official notices depend on manual entry.
- Alternative-corridor screening compares **sampled locations**, not verified legal routes or navigation directions.
- Rainfall-to-flood-to-traffic and power-to-signals-to-congestion links are illustrative, not field-calibrated engineering predictions.
- The RandomForest is trained entirely on synthetic data; its synthetic holdout accuracy is **not** evidence of real disruption prediction ability.
- Economic assumptions represent possible exposure only; numbers are **not** measured revenue, GDP, tax impact, or established monetary losses.
- If a live API is unavailable, the application continues in a clearly labeled offline demo mode rather than inventing measurements.

## CitySync 3.1 — Spatial intelligence and emergency planning update

The **Spatial & emergency AI** workspace adds a cross-area operational planning screen for the seven configured Bengaluru sample locations:

- **Power demand prioritization:** Adjust demand, planning hour (IST), and view *relative* assumed load and critical-service rankings in all seven areas. This does **not** read BESCOM feeder consumption, report megawatts, or move power between feeders.
- **Pipeline/chamber rain screening:** Adjust rainfall and assumed drainage fill to view chamber overflow and pipeline vulnerability indices, map overlays, and field-inspection recommendations. There is **no verified underground asset geometry or condition sensor feed**.
- **Emergency ambulance corridor review:** Select two monitored areas and a planning hour to get a human-coordination checklist, plus latest known TomTom sampled-road observations when available. **No real ambulance location, legal drivable route, reliable ETA, hospital availability, dispatch, traffic-light control, or automatic signal override is provided.** This must never be used as a live emergency navigation tool.
- **Continuous dashboard view updates:** The browser polls stored source readings and recomputes planning screens **every 20 seconds**. TomTom API collection remains on its configured collection interval (typically **15 minutes**) to stay within API usage budgets. Data stays unchanged until a new real source observation arrives, and delayed records remain labeled delayed. No fabricated live fluctuations.
- **Existing ML remains:** The RandomForest model in the Digital Twin tab still learns only from **synthetic** scenario-generator labels and has no demonstrated accuracy on real Bengaluru outages, flooding, pipe breaks or ambulance movement. Spatial screening is explicitly **rule-based**, not a trained forecasting system.

**New API:** `POST /api/twin/spatial-intelligence`

Example local request (PowerShell):

```powershell
$scenario = @{ rainfall_mm_h=130; drainage_fill_pct=90; electricity_demand_pct=120; hour=18; ambulance=$true; ambulance_from='silk_board'; ambulance_to='hebbal' } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:5000/api/twin/spatial-intelligence -Body $scenario -ContentType 'application/json'
```

No extra Python dependencies, secrets, or database migration are required for this update. Stop the old server, back up `.env` and `citysync.db`, and use the new complete ZIP or apply only `advanced_intelligence.py`, `twin_api.py`, and `static/command.js` from the upgrade patch. Never overwrite your private `.env` or existing database.

If future official feeder telemetry, pipeline asset maps and pressure sensors, traffic-signal coordination interfaces, or authorized ambulance GPS streams become available, the data contracts can be extended; only then could these planning screens be evaluated against reality. **The present prototype is not suitable for real emergency decisions or utility switching.**


## FINAL DATA ADDITION — 2025 monthly historical references (no credentials required)

The `/operations` page now includes **three historical monthly graphs** with January–December 2025 values, independent of the TomTom API key:

1. **Karnataka electricity**: *statewide monthly peak demand (MW)*, NOT Bengaluru or a feeder. Jan–Mar 2025 use the **2024–25 financial-year** CEA column, and Apr–Nov 2025 use the **2025–26** CEA column. CEA's report did not include December 2025 in its 2025–26 column, so December is a **secondary-source approximate 17.2 GW** value, visibly identified as such. Official source: https://www.cea.nic.in/api/dashboardReports/view-pdf/en/1b4f1f72-9292-42d8-b5d0-436214490c40 ; secondary December reference: https://www.energyproject.in/grid/state/karnataka
2. **Bengaluru rainfall**: 2025 monthly precipitation archive totals for Bengaluru from https://climateyearbook.com/locations/bengaluru/2025 (based on Open-Meteo archive data: https://open-meteo.com/en/docs/historical-weather-api). This is a weather archive/reanalysis product rather than a street-level rain gauge.
3. **Water proxy**: a purposely **illustrative runoff depth in mm/month = precipitation mm/month × 0.35**. The multiplier is a *demo assumption*, not calibrated to any Bengaluru drainage catchment. This is **not water-supply volume**, pipeline pressure, reservoir level, confirmed overflow or damage prediction. No invented BWSSB values are shown.

Source values are included in `data/bengaluru_2025_monthly_rainfall.csv` and `data/karnataka_2025_monthly_peak_electricity.csv`. The backend reads them in `historical_baselines.py` and serves them through `/api/v4/overview` under `historical_2025`. Existing automatic alert rules continue to use fresh forecast/live evidence, **not** monthwise historical baseline values. No historical reference graph is presented as live telemetry or validated AI forecast.

**Setup:** From the folder containing `app.py`, run ` .\SETUP_WINDOWS.bat ` once and ` .\START_WINDOWS.bat ` to start; then open `http://127.0.0.1:5000/operations`. Configure `.env` for TomTom/admin as before. No actual credentials are bundled.
