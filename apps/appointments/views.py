from django.utils import timezone
from drf_spectacular.utils import OpenApiExample, OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.subscriptions import IsPatientSubscriptionActive
from apps.appointments import services
from apps.appointments.models import Appointment
from apps.appointments.permissions import IsAppointmentParticipantOrAdmin
from apps.appointments.serializers import (
    AppointmentDoctorNotesSerializer,
    AppointmentRescheduleSerializer,
    AppointmentSerializer,
    AppointmentStatusUpdateSerializer,
    DoctorRatingSerializer,
)
from apps.core.constants import Role
from apps.core.permissions import IsDoctorOrAdmin, IsPatient
from apps.core.serializers import DetailResponseSerializer

_APPOINTMENT_RESPONSE_EXAMPLE = {
    "id": 15,
    "patient": {"id": 2, "email": "sara.ahmed@example.com", "first_name": "Sara", "last_name": "Ahmed"},
    "doctor": {"id": 4, "email": "dr.ayesha@example.com", "first_name": "Ayesha", "last_name": "Malik"},
    "appointment_type": "in_person",
    "scheduled_at": "2026-08-05T10:30:00Z",
    "duration_minutes": 30,
    "status": "pending",
    "meeting_link": "",
    "reason": "Routine 20-week checkup",
    "doctor_notes": "",
    "cancellation_reason": "",
    "created_at": "2026-07-29T14:00:00Z",
    "updated_at": "2026-07-29T14:00:00Z",
}


@extend_schema_view(
    list=extend_schema(
        tags=["Appointments"],
        summary="List appointments",
        description=(
            "Role-scoped: patient sees only their own; doctor sees only their own (not other "
            "doctors' appointments with a shared patient) — `?patient_id=`/`?doctor_id=` have no "
            "effect for a doctor caller. Admin sees all, optionally narrowed with `?patient_id=` "
            "and/or `?doctor_id=`. Paginated."
        ),
        parameters=[
            OpenApiParameter(name="patient_id", type=int, location=OpenApiParameter.QUERY, required=False, description="Admin only: narrow to one patient's appointment history."),
            OpenApiParameter(name="doctor_id", type=int, location=OpenApiParameter.QUERY, required=False, description="Admin only: narrow to one doctor's appointments."),
        ],
        examples=[OpenApiExample("200 OK", value={"count": 1, "next": None, "previous": None, "results": [_APPOINTMENT_RESPONSE_EXAMPLE]}, response_only=True, status_codes=["200"])],
    ),
    retrieve=extend_schema(
        tags=["Appointments"],
        summary="Get a single appointment",
        examples=[OpenApiExample("200 OK", value=_APPOINTMENT_RESPONSE_EXAMPLE, response_only=True, status_codes=["200"])],
    ),
    create=extend_schema(
        tags=["Appointments"],
        summary="Book an appointment",
        description=(
            "Patients book for themselves — any `patient_id` in the payload is ignored/overridden "
            "with the requesting patient. A doctor/admin booking on behalf of a patient **must** "
            "supply `patient_id` (400 otherwise). `appointment_type=video_consultation` does **not** "
            "provision a real video session in v1 — `meeting_link` stays empty until manually filled "
            "in (no live video SDK integration). Booking auto-creates a `PatientDoctorAssignment` "
            "between this patient and doctor if one doesn't already exist, and notifies the doctor."
        ),
        responses={201: AppointmentSerializer, 400: DetailResponseSerializer},
        examples=[
            OpenApiExample(
                "Request — patient booking",
                value={
                    "doctor_id": 4,
                    "appointment_type": "in_person",
                    "scheduled_at": "2026-08-05T10:30:00Z",
                    "duration_minutes": 30,
                    "reason": "Routine 20-week checkup",
                },
                request_only=True,
            ),
            OpenApiExample(
                "Request — admin/doctor booking on behalf of a patient",
                value={
                    "patient_id": 2,
                    "doctor_id": 4,
                    "appointment_type": "video_consultation",
                    "scheduled_at": "2026-08-05T10:30:00Z",
                },
                request_only=True,
            ),
            OpenApiExample("201 Created", value=_APPOINTMENT_RESPONSE_EXAMPLE, response_only=True, status_codes=["201"]),
            OpenApiExample(
                "400 Missing patient_id (non-patient actor)",
                value={"detail": "Required when booking on behalf of a patient.", "errors": {"patient_id": ["Required when booking on behalf of a patient."]}},
                response_only=True,
                status_codes=["400"],
            ),
        ],
    ),
    partial_update=extend_schema(tags=["Appointments"], summary="Update appointment fields (rarely used directly — prefer the /status/ and /doctor-notes/ actions below)"),
)
class AppointmentViewSet(viewsets.ModelViewSet):
    """
    Scoping is bespoke (not PatientScopedQuerysetMixin): an appointment has
    two distinct parties, so a doctor's view must be `doctor=request.user`,
    not "any patient this doctor is assigned to" (which would leak other
    doctors' appointments with a shared patient).
    """

    serializer_class = AppointmentSerializer
    queryset = Appointment.objects.select_related("patient", "doctor")  # for schema introspection only
    http_method_names = ["get", "post", "patch", "head", "options"]
    permission_classes = [permissions.IsAuthenticated, IsAppointmentParticipantOrAdmin, IsPatientSubscriptionActive]

    def get_queryset(self):
        qs = Appointment.objects.select_related("patient", "doctor")
        user = self.request.user
        if user.role == Role.PATIENT:
            return qs.filter(patient=user)
        if user.role == Role.DOCTOR:
            return qs.filter(doctor=user)

        patient_id = self.request.query_params.get("patient_id")
        if patient_id:
            qs = qs.filter(patient_id=patient_id)
        doctor_id = self.request.query_params.get("doctor_id")
        if doctor_id:
            qs = qs.filter(doctor_id=doctor_id)
        return qs

    def perform_create(self, serializer):
        user = self.request.user
        if user.role == Role.PATIENT:
            serializer.save(patient=user)
        else:
            serializer.save()

    @extend_schema(
        tags=["Appointments"],
        summary="Change appointment status",
        description=(
            "State machine, enforced server-side — invalid transitions return 400: "
            "`pending → confirmed | cancelled`, `confirmed → completed | cancelled | no_show`. "
            "`completed`/`cancelled`/`no_show` are terminal (no further transitions). "
            "`cancellation_reason` is only used/stored when `status=cancelled`. "
            "Notifies whichever party didn't make the change (or both, if an admin made it)."
        ),
        request=AppointmentStatusUpdateSerializer,
        responses={200: AppointmentSerializer, 400: DetailResponseSerializer},
        examples=[
            OpenApiExample("Request — confirm", value={"status": "confirmed"}, request_only=True),
            OpenApiExample(
                "Request — cancel",
                value={"status": "cancelled", "cancellation_reason": "Patient has a scheduling conflict"},
                request_only=True,
            ),
            OpenApiExample("200 OK", value=_APPOINTMENT_RESPONSE_EXAMPLE, response_only=True, status_codes=["200"]),
            OpenApiExample(
                "400 Invalid transition",
                value={"detail": "Cannot move an appointment from 'completed' to 'pending'.", "errors": None},
                response_only=True,
                status_codes=["400"],
            ),
        ],
    )
    @action(detail=True, methods=["post"], url_path="status")
    def update_status(self, request, pk=None):
        appointment = self.get_object()
        serializer = AppointmentStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            services.transition_status(
                appointment=appointment,
                new_status=serializer.validated_data["status"],
                actor=request.user,
                cancellation_reason=serializer.validated_data.get("cancellation_reason", ""),
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(AppointmentSerializer(appointment).data)

    @extend_schema(
        tags=["Appointments"],
        summary="Set doctor consultation notes",
        description="Doctor/admin only (patients get 403). Free-text post-consultation notes, fully replaced (not appended) on each call.",
        request=AppointmentDoctorNotesSerializer,
        examples=[
            OpenApiExample("Request", value={"doctor_notes": "Blood pressure normal. Advised increased hydration. Follow-up in 2 weeks."}, request_only=True),
            OpenApiExample("200 OK", value=_APPOINTMENT_RESPONSE_EXAMPLE, response_only=True, status_codes=["200"]),
        ],
    )
    @action(
        detail=True,
        methods=["patch"],
        url_path="doctor-notes",
        permission_classes=[permissions.IsAuthenticated, IsDoctorOrAdmin, IsAppointmentParticipantOrAdmin],
    )
    def doctor_notes(self, request, pk=None):
        appointment = self.get_object()
        serializer = AppointmentDoctorNotesSerializer(appointment, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(AppointmentSerializer(appointment).data)

    @extend_schema(
        tags=["Appointments"],
        summary="Reschedule an appointment",
        description=(
            "Changes `scheduled_at` (and optionally `duration_minutes`) without going through the "
            "status state machine — status is untouched. Only allowed while `pending` or "
            "`confirmed` (400 for a terminal-status appointment: completed/cancelled/no_show). "
            "Notifies whichever party didn't make the change (or both, if an admin made it), same "
            "as `/status/`."
        ),
        request=AppointmentRescheduleSerializer,
        responses={200: AppointmentSerializer, 400: DetailResponseSerializer},
        examples=[
            OpenApiExample("Request", value={"scheduled_at": "2026-08-10T14:00:00Z"}, request_only=True),
            OpenApiExample("200 OK", value=_APPOINTMENT_RESPONSE_EXAMPLE, response_only=True, status_codes=["200"]),
            OpenApiExample(
                "400 Terminal status",
                value={"detail": "Cannot reschedule a completed appointment.", "errors": None},
                response_only=True,
                status_codes=["400"],
            ),
        ],
    )
    @action(detail=True, methods=["patch"], url_path="reschedule")
    def reschedule(self, request, pk=None):
        appointment = self.get_object()
        serializer = AppointmentRescheduleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            services.reschedule_appointment(
                appointment=appointment,
                actor=request.user,
                scheduled_at=serializer.validated_data["scheduled_at"],
                duration_minutes=serializer.validated_data.get("duration_minutes"),
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(AppointmentSerializer(appointment).data)

    @extend_schema(
        tags=["Appointments"],
        summary="Rate a completed appointment (patient only)",
        description=(
            "Patient-only, and only the appointment's own patient. Only allowed once the "
            "appointment is `completed` (400 otherwise), and only once per appointment (400 on a "
            "second attempt) — this is the data behind a doctor's `average_rating`/`total_ratings` "
            "(see `GET /accounts/doctors/`) and the admin dashboard's `average_doctor_rating`."
        ),
        request=DoctorRatingSerializer,
        responses={201: DoctorRatingSerializer, 400: DetailResponseSerializer},
        examples=[
            OpenApiExample("Request", value={"score": 5, "comment": "Very attentive and explained everything clearly."}, request_only=True),
            OpenApiExample("201 Created", value={"id": 1, "score": 5, "comment": "Very attentive and explained everything clearly.", "created_at": "2026-08-06T10:00:00Z"}, response_only=True, status_codes=["201"]),
            OpenApiExample("400 Not completed yet", value={"detail": "Only completed appointments can be rated.", "errors": None}, response_only=True, status_codes=["400"]),
        ],
    )
    @action(detail=True, methods=["post"], url_path="rate", permission_classes=[permissions.IsAuthenticated, IsPatient, IsAppointmentParticipantOrAdmin])
    def rate(self, request, pk=None):
        appointment = self.get_object()
        serializer = DoctorRatingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            rating = services.rate_appointment(
                appointment=appointment,
                score=serializer.validated_data["score"],
                comment=serializer.validated_data.get("comment", ""),
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(DoctorRatingSerializer(rating).data, status=status.HTTP_201_CREATED)
