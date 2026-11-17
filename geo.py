from math import radians, sin, cos, asin, sqrt

BENGALURU_BOX = (12.70, 77.30, 13.30, 77.90)  # lat_min, lon_min, lat_max, lon_max (generous)

def km(a_lat, a_lon, b_lat, b_lon):
    p = radians
    h = sin(p(b_lat - a_lat) / 2) ** 2 + cos(p(a_lat)) * cos(p(b_lat)) * sin(p(b_lon - a_lon) / 2) ** 2
    return 2 * 6371 * asin(sqrt(h))

def in_box(lat, lon):
    a, b, c, d = BENGALURU_BOX
    return a <= lat <= c and b <= lon <= d
