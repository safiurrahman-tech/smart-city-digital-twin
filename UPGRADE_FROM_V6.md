# CitySync V6.1 — safe upgrade and verification (Windows PowerShell)

This update fixes real-baseline selection, misleading illustrative values, and duplicate Decision Lab history. It does **not** add live electricity/water telemetry or a scientifically validated prediction model.

## Option A: use the small patch (recommended)

1. Stop the existing CitySync server with `Ctrl+C` in its terminal.
2. Go to the original V6 folder, containing `app.py` and `START_WINDOWS.bat`.
3. Back up your project if desired (especially `.env` and `citysync.db`).
4. Extract `CitySync_V6_1_Upgrade_Patch.zip`. Copy its **`static` folder contents** over your existing project's `static` folder (select Replace files if prompted). It only replaces `app.js`, `index.html`, and `style.css`, and adds `decision_helpers.js`. No `.env`, database, or backend files are touched.
5. Start the original project: `.\START_WINDOWS.bat` and hard-refresh the dashboard with `Ctrl+Shift+R`.

## Option B: full clean V6.1 project

1. Extract the full ZIP; enter the **inner** `CitySync_V6_1_Improvements` folder containing `app.py`.
2. Run `.\SETUP_WINDOWS.bat`.
3. For **existing** installations only, stop both servers, then copy your old `.env` and `citysync.db` into the new folder. Back them up first. Do not share the files: they may contain secret API keys, admin login credentials and local data.
4. Run `.\START_WINDOWS.bat`. Only run one CitySync server on port 5000.

## Jury demo: real baseline + hypothetical impact

1. Wait for `/api/traffic` to include a point with `LIVE` or `DELAYED` status and both `current_travel_time` and `free_flow_travel_time` readings. A `DELAYED` point is a saved, older TomTom snapshot, **not** live.
2. Open **Decision Lab** or click **Jury demo**. The offline checkbox should be **unchecked**. The source notice should read **TOMTOM BASELINE READY**.
3. Click `B · Backup on` or **Run scenario**. The baseline card should say **Observed road-segment baseline**, and the speed should say **TomTom reported speed**. The intervention outcomes remain **SIMULATED**.
4. Click **Run scenario** a second time with identical settings: the history should not gain a duplicate. A new collected traffic snapshot or changed input can create a new entry. Navigating away and back also must not create a new entry.
5. To demonstrate offline fallback, deliberately check **Use fully illustrative offline demonstration**. Then click Run; the baseline should say **Illustrative baseline — NOT measured** and **Example speed**.
6. The CSV export records which baseline came from TomTom and which was illustrative.

## Quick tests

Run from the project folder:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests
node --test tests_js\test_decision_helpers.cjs
```

Node is optional: the website itself does **not** need Node.js to run. You can still use the site without the Node testing command.

If you still see the old UI, ensure only one Flask instance is running and press `Ctrl+Shift+R`.
