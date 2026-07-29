from django.utils import timezone
from drf_spectacular.utils import OpenApiExample, extend_schema, extend_schema_view
from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.permissions import IsOwnerPatientOrAssignedDoctorOrAdmin, IsPatient
from apps.core.viewsets import PatientScopedQuerysetMixin
from apps.emergency.models import EmergencySOSEvent
from apps.emergency.serializers import EmergencySOSEventSerializer, ResolveSOSSerializer

TAG = "Emergency"

_SOS_RESPONSE_EXAMPLE = {
    "id": 3,
    "patient": {"id": 2, "email": "sara.ahmed@example.com", "first_name": "Sara", "last_name": "Ahmed"},
    "latitude": "24.860700",
    "longitude": "67.009900",
    "status": "active",
    "resolved_at": None,
    "notes": "",
    "created_at": "2026-07-29T16:00:00Z",
}


@extend_schema_view(
    list=extend_schema(
        tags=[TAG],
        summary="List SOS events",
        description="Role-scoped: patient's own; assigned doctor's/admin's view.",
        examples=[OpenApiExample("200 OK", value={"count": 1, "next": None, "previous": None, "results": [_SOS_RESPONSE_EXAMPLE]}, response_only=True, status_codes=["200"])],
    ),
    retrieve=extend_schema(tags=[TAG], summary="Get a single SOS event", examples=[OpenApiExample("200 OK", value=_SOS_RESPONSE_EXAMPLE, response_only=True, status_codes=["200"])]),
    create=extend_schema(
        tags=[TAG],
        summary="Trigger an emergency SOS",
        description=(
            "**Patient-only** — unlike every other clinical endpoint, a doctor/admin can never "
            "trigger this on a patient's behalf (403 for them), since it doesn't make sense for "
            "anyone but the patient in distress to raise it. `latitude`/`longitude` are optional "
            "but strongly recommended (GPS coordinates at the moment of triggering). On creation, "
            "a Celery task immediately fans out a notification (push + WhatsApp) to every doctor "
            "assigned to this patient and all active admins, plus a direct WhatsApp message to the "
            "patient's `emergency_contact_phone` if one is set on their profile — none of that "
            "blocks this request, which returns as soon as the event row is created."
        ),
        examples=[
            OpenApiExample("Request", value={"latitude": 24.8607, "longitude": 67.0099, "notes": "Severe abdominal pain"}, request_only=True),
            OpenApiExample("201 Created", value=_SOS_RESPONSE_EXAMPLE, response_only=True, status_codes=["201"]),
        ],
    ),
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

    @extend_schema(
        tags=[TAG],
        summary="Resolve or dismiss an SOS event",
        description="Patient (their own, e.g. to cancel an accidental trigger), assigned doctor, or admin. `status` must be `resolved` or `false_alarm` — `active` is only ever set at creation.",
        request=ResolveSOSSerializer,
        examples=[
            OpenApiExample("Request — false alarm", value={"status": "false_alarm"}, request_only=True),
            OpenApiExample("Request — resolved", value={"status": "resolved"}, request_only=True),
            OpenApiExample("200 OK", value={**_SOS_RESPONSE_EXAMPLE, "status": "resolved", "resolved_at": "2026-07-29T16:20:00Z"}, response_only=True, status_codes=["200"]),
        ],
    )
    @action(detail=True, methods=["post"])
    def resolve(self, request, pk=None):
        event = self.get_object()
        serializer = ResolveSOSSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        event.status = serializer.validated_data["status"]
        event.resolved_at = timezone.now()
        event.save(update_fields=["status", "resolved_at"])
        return Response(EmergencySOSEventSerializer(event).data)
