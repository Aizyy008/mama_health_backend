from drf_spectacular.utils import OpenApiExample, OpenApiParameter, extend_schema
from rest_framework import generics, permissions
from rest_framework.response import Response

from apps.core.permissions import IsAdmin
from apps.core.utils import resolve_patient_from_request
from apps.reports import services
from apps.reports.serializers import AdminStatsSerializer, PatientSummaryReportSerializer

TAG = "Reports"


@extend_schema(
    tags=[TAG],
    summary="Patient health summary",
    description=(
        "Cross-app aggregation, computed fresh on every request — no caching, no separate report "
        "model. Patient: their own summary (no query params). Doctor/Admin: `?patient_id=<id>` "
        "(doctor must be assigned, or 403). Every field is independently nullable/empty if that "
        "patient has no data yet (e.g. `pregnancy_progress` is `null` if no LMP date is set, "
        "`active_diet_plan` is `null` if none exists) — always null-check on the frontend rather "
        "than assuming presence."
    ),
    parameters=[OpenApiParameter(name="patient_id", type=int, location=OpenApiParameter.QUERY, required=False, description="Required for doctor/admin; omit for patients (implies self).")],
    examples=[
        OpenApiExample(
            "200 OK",
            value={
                "pregnancy_progress": {
                    "lmp_date": "2026-03-10",
                    "edd_date": "2026-12-15",
                    "current_week": 20,
                    "current_day": 3,
                    "percent_complete": 51.8,
                    "trimester": 2,
                    "days_remaining": 138,
                },
                "latest_blood_pressure": {
                    "id": 31, "patient": {"id": 2, "email": "sara.ahmed@example.com", "first_name": "Sara", "last_name": "Ahmed"},
                    "systolic": 118, "diastolic": 76, "pulse": 72, "recorded_at": "2026-07-29T09:00:00Z", "notes": "", "created_at": "2026-07-29T09:00:00Z",
                },
                "latest_blood_sugar": {
                    "id": 18, "patient": {"id": 2, "email": "sara.ahmed@example.com", "first_name": "Sara", "last_name": "Ahmed"},
                    "value_mg_dl": 95, "reading_context": "fasting", "recorded_at": "2026-07-29T07:15:00Z", "notes": "", "created_at": "2026-07-29T07:15:00Z",
                },
                "active_diet_plan": {
                    "id": 5, "patient": {"id": 2, "email": "sara.ahmed@example.com", "first_name": "Sara", "last_name": "Ahmed"},
                    "created_by": {"id": 4, "email": "dr.ayesha@example.com", "first_name": "Ayesha", "last_name": "Malik"},
                    "is_active": True, "hydration_recommendation_ml": 2500, "notes": "", "meals": [], "foods_to_avoid": [],
                    "created_at": "2026-07-20T09:00:00Z", "updated_at": "2026-07-20T09:00:00Z",
                },
                "upcoming_appointments": [
                    {
                        "id": 15, "patient": {"id": 2, "email": "sara.ahmed@example.com", "first_name": "Sara", "last_name": "Ahmed"},
                        "doctor": {"id": 4, "email": "dr.ayesha@example.com", "first_name": "Ayesha", "last_name": "Malik"},
                        "appointment_type": "in_person", "scheduled_at": "2026-08-05T10:30:00Z", "duration_minutes": 30,
                        "status": "confirmed", "meeting_link": "", "reason": "Routine checkup", "doctor_notes": "",
                        "cancellation_reason": "", "created_at": "2026-07-29T14:00:00Z", "updated_at": "2026-07-29T14:00:00Z",
                    }
                ],
                "recent_symptoms": [{"id": 9, "patient": {"id": 2, "email": "sara.ahmed@example.com", "first_name": "Sara", "last_name": "Ahmed"}, "log_date": "2026-07-29", "symptoms": [{"id": 4, "name": "Headache"}], "symptom_ids": [4], "notes": "", "created_at": "2026-07-29T20:00:00Z", "updated_at": "2026-07-29T20:00:00Z"}],
                "medicine_adherence": {"taken": 12, "skipped": 1, "pending": 2},
            },
            response_only=True,
            status_codes=["200"],
        )
    ],
)
class PatientSummaryReportView(generics.GenericAPIView):
    """Patient: own summary. Doctor/Admin: ?patient_id=, assignment-checked for doctors."""

    serializer_class = PatientSummaryReportSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        patient = resolve_patient_from_request(request)
        summary = services.build_patient_summary(patient)
        return Response(self.get_serializer(summary).data)


@extend_schema(
    tags=[TAG],
    summary="System-wide statistics (admin only)",
    description="Admin-only. Counts only — no PDF/export, that's explicitly out of v1 scope. `appointments_this_month` is calendar-month-to-date; `new_patients_this_week` is a trailing 7 days.",
    examples=[
        OpenApiExample(
            "200 OK",
            value={"total_patients": 128, "total_doctors": 9, "total_appointments": 342, "appointments_this_month": 47, "active_sos_events": 0, "new_patients_this_week": 6},
            response_only=True,
            status_codes=["200"],
        )
    ],
)
class AdminStatsView(generics.GenericAPIView):
    serializer_class = AdminStatsSerializer
    permission_classes = [IsAdmin]

    def get(self, request):
        stats = services.build_admin_stats()
        return Response(self.get_serializer(stats).data)
