"""
AQ Attendance System - Geofencing Module
Task: Calculates geographic distance and validates if student GPS coordinates are inside the college campus geofence.
"""

import math

# Default College Campus GPS Coordinates
COLLEGE_LATITUDE = 24.495374689123384
COLLEGE_LONGITUDE = 72.80818369745779

# Maximum Geofence Radius Threshold (in Meters)
MAX_RADIUS_METERS = 800

def distance_meters(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """
    Task: Calculate the Great-Circle distance in meters between two lat/lng coordinates using the Haversine formula.
    """
    R = 6371000  # Earth radius in meters
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def is_within_campus(lat, lng, radius_meters: float = MAX_RADIUS_METERS) -> tuple[bool, float]:
    """
    Task: Validate whether student GPS coordinates are within the college campus geofence boundary.
    Returns: (is_inside: bool, distance_in_meters: float).
    """
    try:
        lat = float(lat)
        lng = float(lng)
    except (TypeError, ValueError):
        return False, -1

    # Basic sanity bounds checking for coordinates
    if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
        return False, -1

    dist = distance_meters(lat, lng, COLLEGE_LATITUDE, COLLEGE_LONGITUDE)
    return dist <= radius_meters, dist
