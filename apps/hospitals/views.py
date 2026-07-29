from drf_spectacular.utils import OpenApiExample, extend_schema
from rest_framework import generics, permissions
from rest_framework.response import Response

from apps.core.serializers import DetailResponseSerializer
from apps.hospitals import services
from apps.hospitals.serializers import HospitalSerializer, NearbyHospitalsQuerySerializer


@extend_schema(
    tags=["Hospitals"],
    summary="Find nearby hospitals",
    description=(
        "Live proxy to Google Places Nearby Search — results are **not** stored in our own "
        "database, this always reflects Google's current data (Redis-cached for up to "
        "`HOSPITAL_CACHE_TTL_SECONDS`, default 1h, by rounded lat/lng so GPS jitter doesn't cost "
        "an extra API call). `lat`/`lng` are query params (patient's current GPS position), "
        "`radius` is in meters (default 5000, max 50000). Returns `503` (not a raw error) if "
        "`GOOGLE_PLACES_API_KEY` isn't configured yet or the upstream call fails — show the "
        "frontend a friendly 'hospital search unavailable' state on 503, it isn't a client bug."
    ),
    parameters=[NearbyHospitalsQuerySerializer],
    responses={200: HospitalSerializer(many=True), 503: DetailResponseSerializer},
    examples=[
        OpenApiExample(
            "200 OK",
            value=[
                {
                    "place_id": "ChIJ_abc123",
                    "name": "City Maternity Hospital",
                    "address": "123 Main St, Karachi",
                    "latitude": 24.8607,
                    "longitude": 67.0099,
                    "rating": 4.2,
                    "is_open_now": True,
                }
            ],
            response_only=True,
            status_codes=["200"],
        ),
        OpenApiExample(
            "503 Not configured / upstream failure",
            value={"detail": "Hospital search hasn't been configured yet. Please try again later.", "errors": None},
            response_only=True,
            status_codes=["503"],
        ),
    ],
)
class NearbyHospitalsView(generics.GenericAPIView):
    serializer_class = HospitalSerializer
    permission_classes = [permissions.IsAuthenticated]
    throttle_scope = "hospitals"

    def get(self, request):
        query = NearbyHospitalsQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        results = services.get_nearby_hospitals(**query.validated_data)
        return Response(HospitalSerializer(results, many=True).data)
