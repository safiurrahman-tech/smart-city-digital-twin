"""Makes TomTom incident lists readable: classify, merge the two-direction duplicates,
and count incidents near each monitored point. Start point only (lines are not buffered)."""
from geo import km

# iconCategory codes as listed in TomTom's Traffic Incidents docs; description text is the fallback.
CATS = {"1": "accident", "6": "jam", "7": "closure", "8": "closure", "9": "roadworks"}
ORDER = ["closure", "accident", "jam", "roadworks", "other"]

def kind_of(i):
    k = CATS.get(str(i.get("category")))
    if k:
        return k
    d = (i.get("description") or "").lower()
    if "closed" in d: return "closure"
    if "roadwork" in d or "road work" in d: return "roadworks"
    if any(w in d for w in ("queuing", "stationary", "slow traffic")): return "jam"
    if "accident" in d: return "accident"
    return "other"

def merge(rows):
    groups = {}
    for r in rows:
        ends = tuple(sorted([(r.get("from_text") or "").strip(), (r.get("to_text") or "").strip()]))
        key = (kind_of(r), (r.get("description") or "").strip(), (r.get("road") or ""), ends)
        g = groups.get(key)
        if g is None:
            g = dict(r); g["kind"] = key[0]; g["directions"] = 0; g["raw_reports"] = 0
            groups[key] = g
        g["directions"] += 1; g["raw_reports"] += 1
        if (r.get("delay_s") or 0) > (g.get("delay_s") or 0):
            g["delay_s"] = r["delay_s"]
    out = list(groups.values())
    out.sort(key=lambda g: (ORDER.index(g["kind"]), -(g.get("delay_s") or 0)))
    return out

def nearby(merged, locations, radius_km=2.0):
    res = {}
    for l in locations:
        near = [g for g in merged if g.get("lat") is not None and km(l["lat"], l["lon"], g["lat"], g["lon"]) <= radius_km]
        res[l["id"]] = {"count": len(near), "radius_km": radius_km,
                        "items": [{"kind": g["kind"], "description": g.get("description"), "road": g.get("road")} for g in near[:5]]}
    return res

def counts(merged):
    c = {k: 0 for k in ORDER}
    for g in merged:
        c[g["kind"]] += 1
    return c
