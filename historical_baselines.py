"""Auditable 2025 historical rainfall and Karnataka aggregate power reference.

Historical data are NEVER passed off as live telemetry. The water overlay is a
transparent, illustrative runoff depth; it is NOT water availability or pipe level.
"""
from pathlib import Path
import csv

DATA = Path(__file__).resolve().parent / "data"
RUNOFF_COEFFICIENT = 0.35  # illustrative generic urban surface assumption, NOT measured


def _read(filename):
    with (DATA / filename).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def monthly_reference():
    rain = _read("bengaluru_2025_monthly_rainfall.csv")
    power = _read("karnataka_2025_monthly_peak_electricity.csv")
    assert len(rain) == len(power) == 12
    series = []
    for r, p in zip(rain, power):
        assert r["month"] == p["month"]
        rain_mm = round(float(r["rainfall_mm"]), 1)
        peak_mw = int(float(p["peak_mw"]))
        series.append({
            "month":r["month"], "year":2025,
            "historical_rainfall_mm":rain_mm,
            "historical_karnataka_peak_mw":peak_mw,
            "illustrative_runoff_depth_mm":round(rain_mm * RUNOFF_COEFFICIENT,1),
            "power_source_class":p["data_type"],
        })
    return {
        "status":"HISTORICAL_REFERENCE_2025_NOT_LIVE",
        "year":2025, "rows":series,
        "sources":{
            "rainfall":"https://climateyearbook.com/locations/bengaluru/2025",
            "rainfall_original":"https://open-meteo.com/en/docs/historical-weather-api",
            "electricity_cea":"https://www.cea.nic.in/api/dashboardReports/view-pdf/en/1b4f1f72-9292-42d8-b5d0-436214490c40",
            "electricity_december":"https://www.energyproject.in/grid/state/karnataka",
        },
        "scope":{
            "rainfall":"2025 monthly Bengaluru location weather archive (model/reanalysis, not rain gauge)",
            "electricity":"2025 monthly peak MW for entire Karnataka state; NOT local city or feeder supply",
            "water":"2025 modelled rainfall-derived runoff depth proxy, not BWSSB water supply or observed flooding",
        },
        "methodology":{
            "runoff_coefficient":RUNOFF_COEFFICIENT,
            "runoff_equation":"illustrative_runoff_depth_mm = monthly_rainfall_mm × 0.35",
            "warning":"Monthly rain is NOT adequate to predict flash flooding, chamber failure or pipe damage. Use hourly forecasts and verified drain data for alerts.",
            "electricity_note":"Jan–Mar are from CEA FY 2024–25; Apr–Nov from CEA FY 2025–26; Dec uses a secondary published 2025 grid compilation (~17.2 GW).",
        },
        "prediction_status":"NOT_A_VALIDATED_FORECAST",
    }
