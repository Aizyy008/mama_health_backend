from drf_spectacular.utils import extend_schema
from rest_framework import generics, permissions
from rest_framework.response import Response

from apps.core.permissions import IsAdmin
from apps.core.utils import resolve_patient_from_request
from apps.reports import services
from apps.reports.serializers import AdminStatsSerializer, PatientSummaryReportSerializer

TAG = "Reports"


@extend_schema(tags=[TAG])
class PatientSummaryReportView(generics.GenericAPIView):
    """Patient: own summary. Doctor/Admin: ?patient_id=, assignment-checked for doctors."""

    serializer_class = PatientSummaryReportSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        patient = resolve_patient_from_request(request)
        summary = services.build_patient_summary(patient)
        return Response(self.get_serializer(summary).data)


@extend_schema(tags=[TAG])
class AdminStatsView(generics.GenericAPIView):
    serializer_class = AdminStatsSerializer
    permission_classes = [IsAdmin]

    def get(self, request):
        stats = services.build_admin_stats()
        return Response(self.get_serializer(stats).data)
