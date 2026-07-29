from django.utils import timezone
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.permissions import IsOwnerPatientOrAssignedDoctorOrAdmin, IsPatient
from apps.core.viewsets import PatientScopedQuerysetMixin
from apps.emergency.models import EmergencySOSEvent
from apps.emergency.serializers import EmergencySOSEventSerializer, ResolveSOSSerializer

TAG = "Emergency"


@extend_schema_view(
    list=extend_schema(tags=[TAG]),
    retrieve=extend_schema(tags=[TAG]),
    create=extend_schema(tags=[TAG]),
)
class EmergencySOSViewSet(PatientScopedQuerysetMixin, viewsets.ModelViewSet):
    """SOS is inherently patient-initiated — unlike other clinical models, a
    doctor/admin can never trigger one 'on behalf of' a patient, only read
    and resolve them."""

    serializer_class = EmergencySOSEventSerializer
    queryset = EmergencySOSEvent.objects.select_related("patient")
    http_method_names = ["get", "post", "head", "options"]
    permission_classes = [permissions.IsAuthenticated, IsOwnerPatientOrAssignedDoctorOrAdmin]

    def get_permissions(self):
        if self.action == "create":
            return [permissions.IsAuthenticated(), IsPatient()]
        return super().get_permissions()

    def perform_create(self, serializer):
        serializer.save(patient=self.request.user)

    @extend_schema(tags=[TAG], request=ResolveSOSSerializer)
    @action(detail=True, methods=["post"])
    def resolve(self, request, pk=None):
        event = self.get_object()
        serializer = ResolveSOSSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        event.status = serializer.validated_data["status"]
        event.resolved_at = timezone.now()
        event.save(update_fields=["status", "resolved_at"])
        return Response(EmergencySOSEventSerializer(event).data)
