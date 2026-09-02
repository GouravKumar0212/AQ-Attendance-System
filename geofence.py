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


# A GPS fix always comes with a reported accuracy (the radius, in meters, of the circle
# the device is 68% confident it's inside). We must not treat a fix as exact - a phone can
# report accuracy=1200 (i.e. "I could be anywhere in a 1.2km circle") and that is a
# perfectly normal, honest reading indoors. Silently trusting the raw lat/lng in that case
# is what produces the "1.8km away" false rejections even though the phone is on campus.

# Fixes worse than this are effectively useless for an 800m geofence - ask the student to
# retry instead of silently accepting/rejecting based on noise.
MAX_ACCEPTABLE_ACCURACY_METERS = 300

# How much of the reported accuracy we forgive when checking the boundary. We don't add the
# *entire* accuracy value to the radius (that would let someone 1km away in through a bad fix),
# we add a capped fraction of it, biased in the student's favor only near the boundary.
ACCURACY_BUFFER_CAP_METERS = 150


def is_within_campus(lat, lng, radius_meters: float = MAX_RADIUS_METERS, accuracy: float = None) -> tuple[bool, float]:
    """
    Task: Validate whether student GPS coordinates are within the college campus geofence boundary.

    accuracy: the accuracy (meters) reported by the browser's Geolocation API
              (position.coords.accuracy), if available. Used to add a small, capped
              tolerance to the radius so that a slightly noisy-but-honest fix near the
              boundary isn't rejected, without opening the geofence up wide enough to be
              gamed from far away.

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

    effective_radius = radius_meters
    if accuracy is not None:
        try:
            accuracy = float(accuracy)
            if accuracy > 0:
                effective_radius = radius_meters + min(accuracy, ACCURACY_BUFFER_CAP_METERS)
        except (TypeError, ValueError):
            pass

    return dist <= effective_radius, dist
