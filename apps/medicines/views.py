from django.utils import timezone
from drf_spectacular.utils import OpenApiExample, extend_schema, extend_schema_view
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

_REMINDER_RESPONSE_EXAMPLE = {
    "id": 8,
    "patient": {"id": 2, "email": "sara.ahmed@example.com", "first_name": "Sara", "last_name": "Ahmed"},
    "medicine_name": "Folic Acid",
    "dosage": "5mg",
    "times_per_day": 2,
    "reminder_times": ["08:00", "20:00"],
    "start_date": "2026-07-01",
    "end_date": None,
    "is_active": True,
    "created_at": "2026-07-01T08:00:00Z",
    "updated_at": "2026-07-01T08:00:00Z",
}


@extend_schema_view(
    list=extend_schema(tags=[TAG], summary="List medicine reminders", examples=[OpenApiExample("200 OK", value={"count": 1, "next": None, "previous": None, "results": [_REMINDER_RESPONSE_EXAMPLE]}, response_only=True, status_codes=["200"])]),
    retrieve=extend_schema(tags=[TAG], summary="Get a single medicine reminder", examples=[OpenApiExample("200 OK", value=_REMINDER_RESPONSE_EXAMPLE, response_only=True, status_codes=["200"])]),
    create=extend_schema(
        tags=[TAG],
        summary="Create a medicine reminder",
        description=(
            "Patient-owned — patients create their own (any `patient_id` sent is ignored/"
            "overridden); a doctor/admin acting on a patient's behalf must supply `patient_id` "
            "(doctor must be assigned, or 400). `reminder_times` is a list of `\"HH:MM\"` 24-hour "
            "strings, one per dose per day — the Celery Beat job `send_medicine_reminders` scans "
            "these every 5 minutes and pushes a notification + creates a pending intake log when "
            "a time is due. `end_date` is optional/nullable — leave unset for an ongoing reminder."
        ),
        examples=[
            OpenApiExample("Request", value={"medicine_name": "Folic Acid", "dosage": "5mg", "times_per_day": 2, "reminder_times": ["08:00", "20:00"], "start_date": "2026-07-01"}, request_only=True),
            OpenApiExample("201 Created", value=_REMINDER_RESPONSE_EXAMPLE, response_only=True, status_codes=["201"]),
        ],
    ),
    update=extend_schema(tags=[TAG], summary="Replace a medicine reminder"),
    partial_update=extend_schema(tags=[TAG], summary="Update a medicine reminder", description="E.g. `{\"is_active\": false}` to stop reminders without deleting history.", examples=[OpenApiExample("Request", value={"is_active": False}, request_only=True)]),
    destroy=extend_schema(tags=[TAG], summary="Delete a medicine reminder"),
)
class MedicineReminderViewSet(PatientScopedQuerysetMixin, PatientOwnedCreateMixin, viewsets.ModelViewSet):
    serializer_class = MedicineReminderSerializer
    queryset = MedicineReminder.objects.select_related("patient")
    permission_classes = [permissions.IsAuthenticated, IsOwnerPatientOrAssignedDoctorOrAdmin]

    @extend_schema(
        tags=[TAG],
        summary="Log a dose as taken/skipped",
        description=(
            "Manually records an intake event for this reminder — used both for patient "
            "self-reporting (tapping 'taken'/'skip' on a reminder notification) and for the "
            "automatic pending log the Celery Beat job creates when a scheduled time is reached "
            "(which the patient then updates via this same action). `scheduled_for` defaults to "
            "now if omitted; `taken_at` is auto-set to now only when `status=taken`."
        ),
        request=LogIntakeSerializer,
        responses={201: MedicineIntakeLogSerializer},
        examples=[
            OpenApiExample("Request — taken", value={"status": "taken"}, request_only=True),
            OpenApiExample("Request — skipped, backdated", value={"status": "skipped", "scheduled_for": "2026-07-29T08:00:00Z"}, request_only=True),
            OpenApiExample(
                "201 Created",
                value={"id": 55, "reminder": 8, "scheduled_for": "2026-07-29T08:00:00Z", "taken_at": "2026-07-29T08:05:00Z", "status": "taken", "created_at": "2026-07-29T08:05:00Z"},
                response_only=True,
                status_codes=["201"],
            ),
        ],
    )
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
    list=extend_schema(
        tags=[TAG],
        summary="List medicine intake logs (adherence history)",
        description="Read-only. Role-scoped via the reminder's patient (patient's own logs; assigned doctor's/admin's view). Useful for building an adherence chart (taken vs. skipped vs. pending over time).",
        examples=[OpenApiExample("200 OK (one entry)", value={"id": 55, "reminder": 8, "scheduled_for": "2026-07-29T08:00:00Z", "taken_at": "2026-07-29T08:05:00Z", "status": "taken", "created_at": "2026-07-29T08:05:00Z"}, response_only=True, status_codes=["200"])],
    ),
    retrieve=extend_schema(
        tags=[TAG],
        summary="Get a single intake log entry",
        examples=[OpenApiExample("200 OK", value={"id": 55, "reminder": 8, "scheduled_for": "2026-07-29T08:00:00Z", "taken_at": "2026-07-29T08:05:00Z", "status": "taken", "created_at": "2026-07-29T08:05:00Z"}, response_only=True, status_codes=["200"])],
    ),
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
