# CitySync — road sampling quality checklist

**Current status:** All seven points are illustrative sampling coordinates, not manually verified road selections. The TomTom Flow API successfully collected seven snapshots on 2026-11-17, but the specific road class/name at each sampled coordinate has not been independently established.

## Before presenting

1. Launch CitySync and open **Traffic**.
2. Click **Inspect sampled road** for each monitoring point. The orange dashed line is the polyline returned by TomTom for the nearest matched road segment. The point marker is your query coordinate. Roads can be service roads, flyovers, ramps or side lanes; neither a high nor a low normal speed proves which road you sampled.
3. Compare the line with the named main road you intend to monitor, using the visible map and, where possible, an authoritative road view. Record whether it is a main carriageway, ramp, service lane, or unknown. The TomTom `frc` field is a functional road class code, not a road-name verification.
4. If the wrong segment is selected, adjust the coordinates in `locations.py` *only after finding a suitable point on the intended segment*. Restart Flask so the collector uses the new location values. Validate the new matched polyline before publishing claims.
5. Back up `citysync.db` before moving points. This version excludes historical records at previous coordinates from the latest traffic, history view and Decision Lab, to avoid mixing different road segments. It never deletes that old history.
6. For a defensible Phase 1 claim, describe each reading as “nearest TomTom road segment to [location], collected at [time].” Do not claim it measures a whole junction, neighbourhood or traffic-signal state.

### Location review register (fill in manually)

| Monitoring point | Initial concern / sample | Road geometry inspected? | Intended road verified? | Action |
|---|---|---|---|---|
| Silk Board | 41 km/h free-flow at original point; could be ramp/flyover | No | No | Inspect |
| Electronic City | 25 km/h free-flow at original point; could be a slower road | No | No | Inspect |
| Whitefield | 31 km/h free-flow at original point | No | No | Inspect |
| KR Puram | 52 km/h free-flow at original point | No | No | Inspect |
| Hebbal | 48 km/h free-flow at original point | No | No | Inspect |
| Jayanagar | 18 km/h free-flow at original point; could be local road | No | No | Inspect |
| Yelahanka | 38 km/h free-flow at original point | No | No | Inspect |

## Incident interpretation

- Counts represent **TomTom records** in the configured *city-wide bounding rectangle*, not unique local disruptions in the seven areas.
- Opposing directions may yield separate entries. Avoid summing them as independent failures without matching IDs, geometries, direction and time windows.
- A closure may reflect planned roadworks; missing `delay_s` means the provider gave no delay estimate, not zero delay.

## Trend interpretation

- The app records actual samples only when its flow collector runs. Data from before the app began collecting are not shown, and sample values are never invented.
- The history panel displays sample count and time span. At least four snapshots spanning 30+ minutes are needed to display a minimally informative curve, though much longer history is needed for reliable forecasting.
- Seven flow requests per 15-minute collection cycle cost API quota. Monitor your TomTom account and choose an interval consistent with your allowance; the local app budget is not the provider's billing limit.

## Source and simulation boundary

- Traffic speed, free-flow speed, and travel time: TomTom Flow measurements for the matched road segment.
- Road polyline: TomTom Flow `coordinates.coordinate` (stored locally on collection).
- Electricity percentages, grid outages, signal failure assumptions and additional delay estimates: **hypothetical Decision Lab values**. Not BESCOM data and not a validated forecast.
