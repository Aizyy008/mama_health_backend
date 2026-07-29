from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.permissions import IsDoctorOrAdmin, IsOwnerPatientOrAssignedDoctorOrAdmin
from apps.core.utils import resolve_patient_from_request
from apps.core.viewsets import PatientScopedQuerysetMixin
from apps.diet.models import DietPlan
from apps.diet.serializers import DietPlanSerializer

TAG = "Diet"


@extend_schema_view(
    list=extend_schema(tags=[TAG]),
    retrieve=extend_schema(tags=[TAG]),
    create=extend_schema(tags=[TAG]),
    update=extend_schema(tags=[TAG]),
    partial_update=extend_schema(tags=[TAG]),
    destroy=extend_schema(tags=[TAG]),
)
class DietPlanViewSet(PatientScopedQuerysetMixin, viewsets.ModelViewSet):
    """Doctor/admin authored; patient is read-only (never creates/edits their own plan)."""

    serializer_class = DietPlanSerializer
    queryset = DietPlan.objects.select_related("patient", "created_by").prefetch_related(
        "meals", "foods_to_avoid"
    )
    permission_classes = [permissions.IsAuthenticated, IsOwnerPatientOrAssignedDoctorOrAdmin]

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update", "destroy"):
            return [permissions.IsAuthenticated(), IsDoctorOrAdmin()]
        return super().get_permissions()

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @extend_schema(tags=[TAG])
    @action(detail=False, methods=["get"])
    def active(self, request):
        patient = resolve_patient_from_request(request)
        plan = DietPlan.objects.filter(patient=patient, is_active=True).first()
        if not plan:
            return Response({"detail": "No active diet plan found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(DietPlanSerializer(plan).data)
