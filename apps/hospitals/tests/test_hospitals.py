from unittest.mock import Mock, patch

import pytest
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse
from rest_framework import status

from apps.hospitals import services

pytestmark = pytest.mark.django_db

FAKE_PLACES_RESPONSE = {
    "results": [
        {
            "place_id": "abc123",
            "name": "City Maternity Hospital",
            "vicinity": "123 Main St",
            "geometry": {"location": {"lat": 24.86, "lng": 67.01}},
            "rating": 4.2,
            "opening_hours": {"open_now": True},
        }
    ]
}


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    yield
    cache.clear()


class TestCacheKey:
    def test_nearby_coordinates_share_a_cache_key(self):
        key1 = services.build_cache_key(24.8607123, 67.0099876, 5000)
        key2 = services.build_cache_key(24.8607555, 67.0099111, 5000)
        assert key1 == key2

    def test_different_radius_produces_different_key(self):
        key1 = services.build_cache_key(24.86, 67.01, 5000)
        key2 = services.build_cache_key(24.86, 67.01, 10000)
        assert key1 != key2


class TestNearbyHospitalsEndpoint:
    @override_settings(GOOGLE_PLACES_API_KEY="fake-key-for-test")
    def test_returns_parsed_results(self, patient_client):
        with patch("apps.hospitals.services.requests.get") as mock_get:
            mock_get.return_value = Mock(status_code=200, json=lambda: FAKE_PLACES_RESPONSE)
            mock_get.return_value.raise_for_status = lambda: None
            resp = patient_client.get(reverse("hospitals-nearby"), {"lat": 24.86, "lng": 67.01})
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data[0]["name"] == "City Maternity Hospital"
        assert resp.data[0]["latitude"] == 24.86

    @override_settings(GOOGLE_PLACES_API_KEY="fake-key-for-test")
    def test_second_call_uses_cache_not_a_new_request(self, patient_client):
        with patch("apps.hospitals.services.requests.get") as mock_get:
            mock_get.return_value = Mock(status_code=200, json=lambda: FAKE_PLACES_RESPONSE)
            mock_get.return_value.raise_for_status = lambda: None
            patient_client.get(reverse("hospitals-nearby"), {"lat": 24.86, "lng": 67.01})
            patient_client.get(reverse("hospitals-nearby"), {"lat": 24.8601, "lng": 67.0101})
        assert mock_get.call_count == 1

    def test_returns_503_when_api_key_not_configured(self, patient_client):
        # GOOGLE_PLACES_API_KEY is blank in test settings by default
        resp = patient_client.get(reverse("hospitals-nearby"), {"lat": 24.86, "lng": 67.01})
        assert resp.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    @override_settings(GOOGLE_PLACES_API_KEY="fake-key-for-test")
    def test_returns_503_on_upstream_failure(self, patient_client):
        import requests

        with patch("apps.hospitals.services.requests.get", side_effect=requests.RequestException("boom")):
            resp = patient_client.get(reverse("hospitals-nearby"), {"lat": 24.86, "lng": 67.01})
        assert resp.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    def test_invalid_coordinates_rejected(self, patient_client):
        resp = patient_client.get(reverse("hospitals-nearby"), {"lat": 999, "lng": 67.01})
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_requires_authentication(self, anon_client):
        resp = anon_client.get(reverse("hospitals-nearby"), {"lat": 24.86, "lng": 67.01})
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED
