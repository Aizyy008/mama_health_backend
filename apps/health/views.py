from django.db.models import Sum
from django.utils import timezone
from drf_spectacular.utils import OpenApiExample, extend_schema, extend_schema_view
from rest_framework import generics, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.permissions import IsOwnerPatientOrAssignedDoctorOrAdmin, IsPatient
from apps.core.serializers import DetailResponseSerializer
from apps.core.utils import resolve_patient_from_request
from apps.core.viewsets import PatientOwnedCreateMixin, PatientScopedQuerysetMixin
from apps.health import services
from apps.health.models import (
    BabySizeReference,
    BloodPressureReading,
    BloodSugarReading,
    ExerciseVideo,
    KickCountSession,
    KickEvent,
    SurgicalProcedureRecord,
    SymptomLog,
    WaterIntakeEntry,
)
from apps.health.serializers import (
    BabySizeReferenceSerializer,
    BloodPressureReadingSerializer,
    BloodSugarReadingSerializer,
    ExerciseVideoSerializer,
    KickCountSessionSerializer,
    PregnancyProgressSerializer,
    SurgicalProcedureRecordSerializer,
    SymptomLogSerializer,
    WaterIntakeEntrySerializer,
)

TAG = "Health"

_PATIENT_ONLY_WRITE_NOTE = (
    "Patients create/edit their own records (any `patient_id` in the payload is ignored and "
    "overridden). A doctor/admin acting on a patient's behalf must supply `patient_id` and — for "
    "doctors — must have a `PatientDoctorAssignment` with that patient, or the request 400s."
)


_BP_READING_EXAMPLE = {
    "id": 31,
    "patient": {"id": 2, "email": "sara.ahmed@example.com", "first_name": "Sara", "last_name": "Ahmed"},
    "systolic": 118,
    "diastolic": 76,
    "pulse": 72,
    "recorded_at": "2026-07-29T09:00:00Z",
    "notes": "Felt fine",
    "created_at": "2026-07-29T09:00:00Z",
}


@extend_schema_view(
    list=extend_schema(
        tags=[TAG],
        summary="List blood pressure readings",
        description="Role-scoped: patient's own, or an assigned doctor's/admin's view of a patient's readings.",
        examples=[OpenApiExample("200 OK", value={"count": 1, "next": None, "previous": None, "results": [_BP_READING_EXAMPLE]}, response_only=True, status_codes=["200"])],
    ),
    retrieve=extend_schema(tags=[TAG], summary="Get a single blood pressure reading", examples=[OpenApiExample("200 OK", value=_BP_READING_EXAMPLE, response_only=True, status_codes=["200"])]),
    create=extend_schema(
        tags=[TAG],
        summary="Log a blood pressure reading",
        description=_PATIENT_ONLY_WRITE_NOTE,
        examples=[
            OpenApiExample("Request — patient logging own", value={"systolic": 118, "diastolic": 76, "pulse": 72, "notes": "Felt fine"}, request_only=True),
            OpenApiExample("201 Created", value=_BP_READING_EXAMPLE, response_only=True, status_codes=["201"]),
        ],
    ),
    update=extend_schema(tags=[TAG], summary="Replace a blood pressure reading"),
    partial_update=extend_schema(tags=[TAG], summary="Update a blood pressure reading", examples=[OpenApiExample("Request", value={"notes": "Slightly elevated, will recheck tomorrow"}, request_only=True)]),
    destroy=extend_schema(tags=[TAG], summary="Delete a blood pressure reading"),
)
class BloodPressureReadingViewSet(PatientScopedQuerysetMixin, PatientOwnedCreateMixin, viewsets.ModelViewSet):
    serializer_class = BloodPressureReadingSerializer
    queryset = BloodPressureReading.objects.select_related("patient")
    permission_classes = [permissions.IsAuthenticated, IsOwnerPatientOrAssignedDoctorOrAdmin]


_SUGAR_READING_EXAMPLE = {
    "id": 18,
    "patient": {"id": 2, "email": "sara.ahmed@example.com", "first_name": "Sara", "last_name": "Ahmed"},
    "value_mg_dl": 95,
    "reading_context": "fasting",
    "recorded_at": "2026-07-29T07:15:00Z",
    "notes": "",
    "created_at": "2026-07-29T07:15:00Z",
}


@extend_schema_view(
    list=extend_schema(
        tags=[TAG],
        summary="List blood sugar readings",
        examples=[OpenApiExample("200 OK", value={"count": 1, "next": None, "previous": None, "results": [_SUGAR_READING_EXAMPLE]}, response_only=True, status_codes=["200"])],
    ),
    retrieve=extend_schema(tags=[TAG], summary="Get a single blood sugar reading", examples=[OpenApiExample("200 OK", value=_SUGAR_READING_EXAMPLE, response_only=True, status_codes=["200"])]),
    create=extend_schema(
        tags=[TAG],
        summary="Log a blood sugar reading",
        description=_PATIENT_ONLY_WRITE_NOTE + " `reading_context` is one of `fasting`, `post_meal`, `random`.",
        examples=[
            OpenApiExample("Request", value={"value_mg_dl": 95, "reading_context": "fasting", "notes": ""}, request_only=True),
            OpenApiExample("201 Created", value=_SUGAR_READING_EXAMPLE, response_only=True, status_codes=["201"]),
        ],
    ),
    update=extend_schema(tags=[TAG], summary="Replace a blood sugar reading"),
    partial_update=extend_schema(tags=[TAG], summary="Update a blood sugar reading", examples=[OpenApiExample("Request", value={"notes": "Tested after a large meal"}, request_only=True)]),
    destroy=extend_schema(tags=[TAG], summary="Delete a blood sugar reading"),
)
class BloodSugarReadingViewSet(PatientScopedQuerysetMixin, PatientOwnedCreateMixin, viewsets.ModelViewSet):
    serializer_class = BloodSugarReadingSerializer
    queryset = BloodSugarReading.objects.select_related("patient")
    permission_classes = [permissions.IsAuthenticated, IsOwnerPatientOrAssignedDoctorOrAdmin]


_SYMPTOM_LOG_EXAMPLE = {
    "id": 9,
    "patient": {"id": 2, "email": "sara.ahmed@example.com", "first_name": "Sara", "last_name": "Ahmed"},
    "log_date": "2026-07-29",
    "symptoms": [{"id": 1, "name": "Nausea"}, {"id": 4, "name": "Headache"}],
    "notes": "Mild headache in the evening",
    "created_at": "2026-07-29T20:00:00Z",
    "updated_at": "2026-07-29T20:00:00Z",
}


@extend_schema_view(
    list=extend_schema(
        tags=[TAG],
        summary="List symptom logs",
        examples=[OpenApiExample("200 OK", value={"count": 1, "next": None, "previous": None, "results": [_SYMPTOM_LOG_EXAMPLE]}, response_only=True, status_codes=["200"])],
    ),
    retrieve=extend_schema(tags=[TAG], summary="Get a single day's symptom log", examples=[OpenApiExample("200 OK", value=_SYMPTOM_LOG_EXAMPLE, response_only=True, status_codes=["200"])]),
    create=extend_schema(
        tags=[TAG],
        summary="Log today's (or any day's) symptoms — upserts",
        description=(
            "**Upserts by (patient, log_date)** — POSTing again for a date that already has an "
            "entry replaces its `symptoms`/`notes` rather than creating a duplicate. "
            "`symptom_ids` references `SymptomType` IDs (see a separate lookup if you need the "
            "full list — common ones are pre-seeded: Nausea, Vomiting, Fatigue, Headache, Back pain, "
            "Swelling, Heartburn, Constipation, Dizziness, Shortness of breath, Leg cramps, Insomnia, "
            "Mood swings, Frequent urination, Braxton Hicks contractions). `log_date` defaults to "
            "today if omitted."
        ),
        examples=[
            OpenApiExample("Request", value={"log_date": "2026-07-29", "symptom_ids": [1, 4], "notes": "Mild headache in the evening"}, request_only=True),
            OpenApiExample("201 Created", value=_SYMPTOM_LOG_EXAMPLE, response_only=True, status_codes=["201"]),
        ],
    ),
    update=extend_schema(tags=[TAG], summary="Replace a symptom log"),
    partial_update=extend_schema(tags=[TAG], summary="Update a symptom log", description="Same upsert-shaped body as create — usually unnecessary since POSTing again for the same date already upserts (see above).", examples=[OpenApiExample("Request", value={"symptom_ids": [1], "notes": "Nausea improved by evening"}, request_only=True)]),
    destroy=extend_schema(tags=[TAG], summary="Delete a symptom log"),
)
class SymptomLogViewSet(PatientScopedQuerysetMixin, PatientOwnedCreateMixin, viewsets.ModelViewSet):
    """POST upserts by (patient, log_date) — one entry per day, see SymptomLogSerializer.create()."""

    serializer_class = SymptomLogSerializer
    queryset = SymptomLog.objects.select_related("patient").prefetch_related("symptoms")
    permission_classes = [permissions.IsAuthenticated, IsOwnerPatientOrAssignedDoctorOrAdmin]


_WATER_ENTRY_EXAMPLE = {"id": 102, "patient": {"id": 2, "email": "sara.ahmed@example.com", "first_name": "Sara", "last_name": "Ahmed"}, "amount_ml": 250, "logged_at": "2026-07-29T11:00:00Z", "log_date": "2026-07-29", "created_at": "2026-07-29T11:00:00Z"}


@extend_schema_view(
    list=extend_schema(
        tags=[TAG],
        summary="List water intake entries (full history)",
        examples=[OpenApiExample("200 OK", value={"count": 1, "next": None, "previous": None, "results": [_WATER_ENTRY_EXAMPLE]}, response_only=True, status_codes=["200"])],
    ),
    retrieve=extend_schema(tags=[TAG], summary="Get a single water intake entry", examples=[OpenApiExample("200 OK", value=_WATER_ENTRY_EXAMPLE, response_only=True, status_codes=["200"])]),
    create=extend_schema(
        tags=[TAG],
        summary="Log a water intake entry",
        description="Append-only — no update/delete endpoints. Each call adds one entry; `log_date` defaults to today. 'Daily reset' in the UI is purely a display concept: use `GET /water-intake/today/` to get today's running total, `GET /water-intake/` for full history.",
        examples=[
            OpenApiExample("Request", value={"amount_ml": 250}, request_only=True),
            OpenApiExample("201 Created", value=_WATER_ENTRY_EXAMPLE, response_only=True, status_codes=["201"]),
        ],
    ),
)
class WaterIntakeEntryViewSet(PatientScopedQuerysetMixin, PatientOwnedCreateMixin, viewsets.ModelViewSet):
    """No update/delete — water intake is an append-only log; 'today' is a query-time filter, not a reset."""

    serializer_class = WaterIntakeEntrySerializer
    queryset = WaterIntakeEntry.objects.select_related("patient")
    permission_classes = [permissions.IsAuthenticated, IsOwnerPatientOrAssignedDoctorOrAdmin]
    http_method_names = ["get", "post", "head", "options"]

    @extend_schema(
        tags=[TAG],
        summary="Today's water intake total",
        description="Patient-only. Aggregates today's entries into a running total for the water-tracker widget.",
        examples=[
            OpenApiExample(
                "200 OK",
                value={
                    "date": "2026-07-29",
                    "total_ml": 1500,
                    "entries": [
                        {"id": 101, "patient": {"id": 2, "email": "sara.ahmed@example.com", "first_name": "Sara", "last_name": "Ahmed"}, "amount_ml": 250, "logged_at": "2026-07-29T08:00:00Z", "log_date": "2026-07-29", "created_at": "2026-07-29T08:00:00Z"},
                        {"id": 102, "patient": {"id": 2, "email": "sara.ahmed@example.com", "first_name": "Sara", "last_name": "Ahmed"}, "amount_ml": 1250, "logged_at": "2026-07-29T11:00:00Z", "log_date": "2026-07-29", "created_at": "2026-07-29T11:00:00Z"},
                    ],
                },
                response_only=True,
                status_codes=["200"],
            )
        ],
    )
    @action(detail=False, methods=["get"], permission_classes=[permissions.IsAuthenticated, IsPatient])
    def today(self, request):
        today = timezone.localdate()
        qs = self.get_queryset().filter(log_date=today)
        total = qs.aggregate(total_ml=Sum("amount_ml"))["total_ml"] or 0
        return Response(
            {
                "date": today,
                "total_ml": total,
                "entries": WaterIntakeEntrySerializer(qs, many=True).data,
            }
        )


_KICK_SESSION_EXAMPLE = {"id": 7, "patient": {"id": 2, "email": "sara.ahmed@example.com", "first_name": "Sara", "last_name": "Ahmed"}, "started_at": "2026-07-29T15:00:00Z", "ended_at": None, "kick_count": 0, "log_date": "2026-07-29", "events": [], "created_at": "2026-07-29T15:00:00Z"}


@extend_schema_view(
    list=extend_schema(
        tags=[TAG],
        summary="List kick-count sessions (history)",
        examples=[OpenApiExample("200 OK", value={"count": 1, "next": None, "previous": None, "results": [_KICK_SESSION_EXAMPLE]}, response_only=True, status_codes=["200"])],
    ),
    retrieve=extend_schema(tags=[TAG], summary="Get a single kick-count session", examples=[OpenApiExample("200 OK", value=_KICK_SESSION_EXAMPLE, response_only=True, status_codes=["200"])]),
    create=extend_schema(
        tags=[TAG],
        summary="Start a kick-count session",
        description="Starts a new session with `kick_count=0`. Follow up with `/tap/` for each kick felt, then `/end/` when done.",
        examples=[
            OpenApiExample("Request", value={}, request_only=True),
            OpenApiExample("201 Created", value=_KICK_SESSION_EXAMPLE, response_only=True, status_codes=["201"]),
        ],
    ),
)
class KickCountSessionViewSet(PatientScopedQuerysetMixin, PatientOwnedCreateMixin, viewsets.ModelViewSet):
    serializer_class = KickCountSessionSerializer
    queryset = KickCountSession.objects.select_related("patient").prefetch_related("events")
    permission_classes = [permissions.IsAuthenticated, IsOwnerPatientOrAssignedDoctorOrAdmin]
    http_method_names = ["get", "post", "head", "options"]

    @extend_schema(
        tags=[TAG],
        summary="Record one kick",
        description="Call once per kick felt during an active session. Increments `kick_count` and appends a `KickEvent`. 400s if the session has already ended.",
        responses={200: KickCountSessionSerializer, 400: DetailResponseSerializer},
        examples=[
            OpenApiExample("Request", value={}, request_only=True),
            OpenApiExample(
                "200 OK",
                value={"id": 7, "patient": {"id": 2, "email": "sara.ahmed@example.com", "first_name": "Sara", "last_name": "Ahmed"}, "started_at": "2026-07-29T15:00:00Z", "ended_at": None, "kick_count": 1, "log_date": "2026-07-29", "events": [{"id": 40, "tapped_at": "2026-07-29T15:02:00Z"}], "created_at": "2026-07-29T15:00:00Z"},
                response_only=True,
                status_codes=["200"],
            ),
            OpenApiExample("400 Session already ended", value={"detail": "This session has already ended.", "errors": None}, response_only=True, status_codes=["400"]),
        ],
    )
    @action(detail=True, methods=["post"])
    def tap(self, request, pk=None):
        session = self.get_object()
        if session.ended_at:
            return Response({"detail": "This session has already ended."}, status=status.HTTP_400_BAD_REQUEST)
        KickEvent.objects.create(session=session)
        session.kick_count += 1
        session.save(update_fields=["kick_count"])
        return Response(KickCountSessionSerializer(session).data)

    @extend_schema(
        tags=[TAG],
        summary="End a kick-count session",
        description="Sets `ended_at` to now. After this, `/tap/` on the same session 400s.",
        examples=[
            OpenApiExample("Request", value={}, request_only=True),
            OpenApiExample(
                "200 OK",
                value={"id": 7, "patient": {"id": 2, "email": "sara.ahmed@example.com", "first_name": "Sara", "last_name": "Ahmed"}, "started_at": "2026-07-29T15:00:00Z", "ended_at": "2026-07-29T15:20:00Z", "kick_count": 12, "log_date": "2026-07-29", "events": [], "created_at": "2026-07-29T15:00:00Z"},
                response_only=True,
                status_codes=["200"],
            ),
        ],
    )
    @action(detail=True, methods=["post"])
    def end(self, request, pk=None):
        session = self.get_object()
        session.ended_at = timezone.now()
        session.save(update_fields=["ended_at"])
        return Response(KickCountSessionSerializer(session).data)


@extend_schema_view(
    list=extend_schema(
        tags=[TAG],
        summary="List baby-size-by-week reference data",
        description="Static reference data, not per-patient — same content for every user. No pagination.",
        examples=[OpenApiExample("200 OK (excerpt)", value=[{"week": 20, "size_comparison": "a banana", "length_cm": "25.60", "weight_grams": "300.0", "description": ""}], response_only=True, status_codes=["200"])],
    ),
    retrieve=extend_schema(
        tags=[TAG],
        summary="Get baby size for a specific week",
        description="Lookup by week number (1–42), not by database ID — e.g. `GET /api/v1/health/baby-size/20/`.",
        examples=[OpenApiExample("200 OK", value={"week": 20, "size_comparison": "a banana", "length_cm": "25.60", "weight_grams": "300.0", "description": ""}, response_only=True, status_codes=["200"])],
    ),
)
class BabySizeReferenceViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = BabySizeReferenceSerializer
    queryset = BabySizeReference.objects.all()
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = "week"
    pagination_class = None


@extend_schema(
    tags=[TAG],
    summary="Get pregnancy progress",
    description=(
        "Computed on every request from `PatientProfile.lmp_date`/`edd_date` — never stored, so it "
        "can never go stale. Patient: their own progress (no query params needed). Doctor/Admin: "
        "pass `?patient_id=<id>` (doctor must be assigned to that patient, or 403). 404 if the "
        "patient hasn't set an LMP date yet."
    ),
    responses={200: PregnancyProgressSerializer, 404: DetailResponseSerializer},
    examples=[
        OpenApiExample(
            "200 OK",
            value={
                "lmp_date": "2026-03-10",
                "edd_date": "2026-12-15",
                "current_week": 20,
                "current_day": 3,
                "percent_complete": 51.8,
                "trimester": 2,
                "days_remaining": 138,
            },
            response_only=True,
            status_codes=["200"],
        ),
        OpenApiExample("404 LMP not set", value={"detail": "Pregnancy progress unavailable — LMP date not set yet.", "errors": None}, response_only=True, status_codes=["404"]),
    ],
)
class PregnancyProgressView(generics.GenericAPIView):
    """Patient: own progress. Doctor/Admin: ?patient_id=<id>, doctor must be assigned."""

    serializer_class = PregnancyProgressSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        patient = resolve_patient_from_request(request)
        profile = getattr(patient, "patient_profile", None)
        data = services.get_pregnancy_progress(profile) if profile else None
        if data is None:
            return Response(
                {"detail": "Pregnancy progress unavailable — LMP date not set yet."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(self.get_serializer(data).data)


_SURGICAL_PROCEDURE_EXAMPLE = {
    "id": 3,
    "patient": {"id": 2, "email": "sara.ahmed@example.com", "first_name": "Sara", "last_name": "Ahmed"},
    "procedure_name": "C-Section",
    "procedure_date": "2024-03-10",
    "hospital_name": "City Maternity Hospital",
    "notes": "Elective, no complications",
    "created_at": "2026-07-29T10:00:00Z",
    "updated_at": "2026-07-29T10:00:00Z",
}


@extend_schema_view(
    list=extend_schema(
        tags=[TAG],
        summary="List surgical procedure records",
        examples=[OpenApiExample("200 OK", value={"count": 1, "next": None, "previous": None, "results": [_SURGICAL_PROCEDURE_EXAMPLE]}, response_only=True, status_codes=["200"])],
    ),
    retrieve=extend_schema(tags=[TAG], summary="Get a single surgical procedure record", examples=[OpenApiExample("200 OK", value=_SURGICAL_PROCEDURE_EXAMPLE, response_only=True, status_codes=["200"])]),
    create=extend_schema(
        tags=[TAG],
        summary="Log a surgical procedure",
        description=_PATIENT_ONLY_WRITE_NOTE,
        examples=[
            OpenApiExample("Request", value={"procedure_name": "C-Section", "procedure_date": "2024-03-10", "hospital_name": "City Maternity Hospital", "notes": "Elective, no complications"}, request_only=True),
            OpenApiExample("201 Created", value=_SURGICAL_PROCEDURE_EXAMPLE, response_only=True, status_codes=["201"]),
        ],
    ),
    update=extend_schema(tags=[TAG], summary="Replace a surgical procedure record"),
    partial_update=extend_schema(tags=[TAG], summary="Update a surgical procedure record", examples=[OpenApiExample("Request", value={"notes": "Follow-up scan showed full recovery"}, request_only=True)]),
    destroy=extend_schema(tags=[TAG], summary="Delete a surgical procedure record"),
)
class SurgicalProcedureRecordViewSet(
    PatientScopedQuerysetMixin, PatientOwnedCreateMixin, viewsets.ModelViewSet
):
    serializer_class = SurgicalProcedureRecordSerializer
    queryset = SurgicalProcedureRecord.objects.select_related("patient")
    permission_classes = [permissions.IsAuthenticated, IsOwnerPatientOrAssignedDoctorOrAdmin]


@extend_schema_view(
    list=extend_schema(
        tags=[TAG],
        summary="List pregnancy exercise & breathing videos",
        description=(
            "**Read-only reference data — no video files are hosted by this API.** `video_url` is "
            "an external link (YouTube/Vimeo/etc.); the Flutter app is responsible for embedding/"
            "playing it (e.g. in a WebView or a native video-player widget pointed at that URL). "
            "Admin manages entries via Django admin, not through this API — there is no write "
            "endpoint. Filter client-side by `category` (`exercise` | `breathing`) and/or "
            "`trimester` (1/2/3, may be `null` meaning 'suitable for any trimester')."
        ),
        examples=[
            OpenApiExample(
                "200 OK",
                value={
                    "count": 1,
                    "next": None,
                    "previous": None,
                    "results": [
                        {
                            "id": 1,
                            "title": "Prenatal breathing basics",
                            "description": "A gentle 10-minute breathing routine safe for all trimesters.",
                            "category": "breathing",
                            "video_url": "https://www.youtube.com/watch?v=example",
                            "duration_minutes": 10,
                            "trimester": None,
                        }
                    ],
                },
                response_only=True,
                status_codes=["200"],
            )
        ],
    ),
    retrieve=extend_schema(
        tags=[TAG],
        summary="Get a single video's details",
        examples=[
            OpenApiExample(
                "200 OK",
                value={
                    "id": 1,
                    "title": "Prenatal breathing basics",
                    "description": "A gentle 10-minute breathing routine safe for all trimesters.",
                    "category": "breathing",
                    "video_url": "https://www.youtube.com/watch?v=example",
                    "duration_minutes": 10,
                    "trimester": None,
                },
                response_only=True,
                status_codes=["200"],
            )
        ],
    ),
)
class ExerciseVideoViewSet(viewsets.ReadOnlyModelViewSet):
    """Admin-managed via Django admin (like BabySizeReference) — no write API. video_url is
    rendered/played by the Flutter frontend; this API only ever returns the link + metadata."""

    serializer_class = ExerciseVideoSerializer
    queryset = ExerciseVideo.objects.all()
    permission_classes = [permissions.IsAuthenticated]
