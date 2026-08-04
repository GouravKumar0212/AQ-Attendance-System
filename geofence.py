import math

COLLEGE_LATITUDE = 24.495374689123384
COLLEGE_LONGITUDE = 72.80818369745779

MAX_RADIUS_METERS = 100

def distance_meters(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance between two lat/lng points, in meters (Haversine formula)."""
    R = 6371000  # Earth radius in meters
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def is_within_campus(lat, lng, radius_meters: float = MAX_RADIUS_METERS) -> tuple[bool, float]:
    """
    Returns (is_inside, distance_in_meters).
    Returns (False, -1) if lat/lng are missing or malformed.
    """
    try:
        lat = float(lat)
        lng = float(lng)
    except (TypeError, ValueError):
        return False, -1

    # Basic sanity bounds so garbage/spoofed values don't slip through
    if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
        return False, -1

    dist = distance_meters(lat, lng, COLLEGE_LATITUDE, COLLEGE_LONGITUDE)
    return dist <= radius_meters, dist
