from django.utils import timezone
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.permissions import IsOwnerPatientOrAssignedDoctorOrAdmin
from apps.core.viewsets import PatientOwnedCreateMixin, PatientScopedQuerysetMixin
from apps.medicines.models import MedicineIntakeLog, MedicineReminder
from apps.medicines.serializers import (
    LogIntakeSerializer,
    MedicineIntakeLogSerializer,
    MedicineReminderSerializer,
)

TAG = "Medicines"


@extend_schema_view(
    list=extend_schema(tags=[TAG]),
    retrieve=extend_schema(tags=[TAG]),
    create=extend_schema(tags=[TAG]),
    update=extend_schema(tags=[TAG]),
    partial_update=extend_schema(tags=[TAG]),
    destroy=extend_schema(tags=[TAG]),
)
class MedicineReminderViewSet(PatientScopedQuerysetMixin, PatientOwnedCreateMixin, viewsets.ModelViewSet):
    serializer_class = MedicineReminderSerializer
    queryset = MedicineReminder.objects.select_related("patient")
    permission_classes = [permissions.IsAuthenticated, IsOwnerPatientOrAssignedDoctorOrAdmin]

    @extend_schema(tags=[TAG], request=LogIntakeSerializer)
    @action(detail=True, methods=["post"], url_path="log-intake")
    def log_intake(self, request, pk=None):
        reminder = self.get_object()
        serializer = LogIntakeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        intake_status = serializer.validated_data["status"]
        log = MedicineIntakeLog.objects.create(
            reminder=reminder,
            scheduled_for=serializer.validated_data["scheduled_for"],
            taken_at=timezone.now() if intake_status == MedicineIntakeLog.Status.TAKEN else None,
            status=intake_status,
        )
        return Response(MedicineIntakeLogSerializer(log).data, status=201)


@extend_schema_view(
    list=extend_schema(tags=[TAG]),
    retrieve=extend_schema(tags=[TAG]),
)
class MedicineIntakeLogViewSet(PatientScopedQuerysetMixin, viewsets.ReadOnlyModelViewSet):
    """
    No object-level permission class here (unlike other clinical viewsets):
    IsOwnerPatientOrAssignedDoctorOrAdmin checks obj.patient_id directly,
    but MedicineIntakeLog only has that indirectly via `reminder.patient` —
    it would wrongly 403 even the rightful owner. get_queryset() scoping
    (patient_field_name="reminder__patient") already fully protects both
    list and retrieve for a read-only viewset, so it's not needed here.
    """

    serializer_class = MedicineIntakeLogSerializer
    queryset = MedicineIntakeLog.objects.select_related("reminder", "reminder__patient")
    permission_classes = [permissions.IsAuthenticated]
    patient_field_name = "reminder__patient"
