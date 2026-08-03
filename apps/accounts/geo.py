import math


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """
    Great-circle distance in kilometers between two lat/lng points.
    Plain-math, no external API/key — the client explicitly rejected a
    paid maps API for "near me" doctor search in favor of this.
    """
    earth_radius_km = 6371.0
    lat1_rad, lng1_rad, lat2_rad, lng2_rad = map(math.radians, (lat1, lng1, lat2, lng2))
    dlat = lat2_rad - lat1_rad
    dlng = lng2_rad - lng1_rad
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlng / 2) ** 2
    c = 2 * math.asin(math.sqrt(a))
    return earth_radius_km * c
