from drf_spectacular.utils import extend_schema
from rest_framework import generics, permissions
from rest_framework.response import Response

from apps.hospitals import services
from apps.hospitals.serializers import HospitalSerializer, NearbyHospitalsQuerySerializer


@extend_schema(tags=["Hospitals"], parameters=[NearbyHospitalsQuerySerializer], responses=HospitalSerializer(many=True))
class NearbyHospitalsView(generics.GenericAPIView):
    serializer_class = HospitalSerializer
    permission_classes = [permissions.IsAuthenticated]
    throttle_scope = "hospitals"

    def get(self, request):
        query = NearbyHospitalsQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        results = services.get_nearby_hospitals(**query.validated_data)
        return Response(HospitalSerializer(results, many=True).data)
