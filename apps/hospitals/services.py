import requests
from django.conf import settings
from django.core.cache import cache

from apps.hospitals.exceptions import HospitalsUnavailable

GOOGLE_PLACES_NEARBY_URL = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"


def build_cache_key(lat: float, lng: float, radius: int, precision: int = 3) -> str:
    """Rounds lat/lng to ~110m grid cells (3 decimal places) so nearby
    requests share a cache entry rather than every GPS jitter triggering a
    fresh, billed Places API call."""
    return f"hospitals:nearby:{round(lat, precision)}:{round(lng, precision)}:{radius}"


def get_nearby_hospitals(*, lat: float, lng: float, radius: int = 5000) -> list[dict]:
    cache_key = build_cache_key(lat, lng, radius)
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    if not settings.GOOGLE_PLACES_API_KEY:
        raise HospitalsUnavailable("Hospital search hasn't been configured yet. Please try again later.")

    params = {
        "location": f"{lat},{lng}",
        "radius": radius,
        "type": "hospital",
        "key": settings.GOOGLE_PLACES_API_KEY,
    }
    try:
        response = requests.get(GOOGLE_PLACES_NEARBY_URL, params=params, timeout=5)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise HospitalsUnavailable(
            "Couldn't reach the hospital search service. Please try again shortly."
        ) from exc

    results = _parse_places_response(response.json())
    cache.set(cache_key, results, timeout=settings.HOSPITAL_CACHE_TTL_SECONDS)
    return results


def _parse_places_response(payload: dict) -> list[dict]:
    hospitals = []
    for place in payload.get("results", []):
        location = place.get("geometry", {}).get("location", {})
        hospitals.append(
            {
                "place_id": place.get("place_id"),
                "name": place.get("name"),
                "address": place.get("vicinity"),
                "latitude": location.get("lat"),
                "longitude": location.get("lng"),
                "rating": place.get("rating"),
                "is_open_now": place.get("opening_hours", {}).get("open_now"),
            }
        )
    return hospitals
