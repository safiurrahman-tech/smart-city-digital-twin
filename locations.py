"""Representative monitoring points. Coordinates are APPROXIMATE junction/neighbourhood centres
chosen by the project team. Verify against an authoritative map before publishing claims.
A traffic reading applies only to the road segment nearest the point, not to the whole area.
See ROAD_REVIEW_CHECKLIST.md; road suitability is not yet verified.
If coordinates change, historical records are kept but excluded from new charts and simulations."""
LOCATIONS = [
    {"id": "silk_board", "name": "Silk Board Junction", "lat": 12.9177, "lon": 77.6238},
    {"id": "electronic_city", "name": "Electronic City", "lat": 12.8452, "lon": 77.6602},
    {"id": "whitefield", "name": "Whitefield", "lat": 12.9698, "lon": 77.7500},
    {"id": "kr_puram", "name": "KR Puram", "lat": 13.0035, "lon": 77.6958},
    {"id": "hebbal", "name": "Hebbal", "lat": 13.0358, "lon": 77.5970},
    {"id": "jayanagar", "name": "Jayanagar", "lat": 12.9308, "lon": 77.5838},
    {"id": "yelahanka", "name": "Yelahanka", "lat": 13.1007, "lon": 77.5963},
]
BY_ID = {l["id"]: l for l in LOCATIONS}


def get_locations():
    """Current configured monitoring points for collectors and impact rules."""
    return LOCATIONS


def load_overrides():
    """Load admin-approved monitoring locations from persistent SQLite storage."""
    import db
    with db.conn() as connection:
        rows = connection.execute("SELECT location_id, lat, lon FROM location_overrides").fetchall()
    for row in rows:
        point = BY_ID.get(row["location_id"])
        if point is not None:
            point.update(lat=float(row["lat"]), lon=float(row["lon"]))
