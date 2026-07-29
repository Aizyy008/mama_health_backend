from drf_spectacular.utils import OpenApiExample, extend_schema, extend_schema_view
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.permissions import IsDoctorOrAdmin, IsOwnerPatientOrAssignedDoctorOrAdmin
from apps.core.serializers import DetailResponseSerializer
from apps.core.utils import resolve_patient_from_request
from apps.core.viewsets import PatientScopedQuerysetMixin
from apps.diet.models import DietPlan
from apps.diet.serializers import DietPlanSerializer

TAG = "Diet"

_DIET_PLAN_RESPONSE_EXAMPLE = {
    "id": 5,
    "patient": {"id": 2, "email": "sara.ahmed@example.com", "first_name": "Sara", "last_name": "Ahmed"},
    "created_by": {"id": 4, "email": "dr.ayesha@example.com", "first_name": "Ayesha", "last_name": "Malik"},
    "is_active": True,
    "hydration_recommendation_ml": 2500,
    "notes": "Increase iron-rich foods this trimester.",
    "meals": [
        {"id": 11, "meal_type": "breakfast", "description": "Oatmeal with fruit and a boiled egg"},
        {"id": 12, "meal_type": "lunch", "description": "Grilled chicken, brown rice, steamed vegetables"},
    ],
    "foods_to_avoid": [{"id": 6, "food_name": "Raw fish", "reason": "Food safety during pregnancy"}],
    "created_at": "2026-07-20T09:00:00Z",
    "updated_at": "2026-07-20T09:00:00Z",
}


@extend_schema_view(
    list=extend_schema(
        tags=[TAG],
        summary="List diet plans",
        description="Role-scoped: patient's own plans (all history, active + inactive), or an assigned doctor's/admin's view.",
        examples=[OpenApiExample("200 OK", value={"count": 1, "next": None, "previous": None, "results": [_DIET_PLAN_RESPONSE_EXAMPLE]}, response_only=True, status_codes=["200"])],
    ),
    retrieve=extend_schema(tags=[TAG], summary="Get a single diet plan", examples=[OpenApiExample("200 OK", value=_DIET_PLAN_RESPONSE_EXAMPLE, response_only=True, status_codes=["200"])]),
    create=extend_schema(
        tags=[TAG],
        summary="Create a diet plan (doctor/admin only)",
        description=(
            "Doctor/admin only — patients get 403 (diet plans are doctor-authored, never "
            "self-edited). Doctor must be assigned to `patient_id` or 400. Creating a new plan "
            "**deactivates** (never deletes) any previous active plan for that patient — full "
            "history is preserved and queryable via the list endpoint. `meals`/`foods_to_avoid` "
            "are nested and written in the same request (no separate sub-endpoints)."
        ),
        examples=[
            OpenApiExample(
                "Request",
                value={
                    "patient_id": 2,
                    "hydration_recommendation_ml": 2500,
                    "notes": "Increase iron-rich foods this trimester.",
                    "meals": [
                        {"meal_type": "breakfast", "description": "Oatmeal with fruit and a boiled egg"},
                        {"meal_type": "lunch", "description": "Grilled chicken, brown rice, steamed vegetables"},
                    ],
                    "foods_to_avoid": [{"food_name": "Raw fish", "reason": "Food safety during pregnancy"}],
                },
                request_only=True,
            ),
            OpenApiExample("201 Created", value=_DIET_PLAN_RESPONSE_EXAMPLE, response_only=True, status_codes=["201"]),
        ],
    ),
    update=extend_schema(tags=[TAG], summary="Replace a diet plan (doctor/admin only)"),
    partial_update=extend_schema(
        tags=[TAG],
        summary="Update a diet plan (doctor/admin only)",
        description="`meals`/`foods_to_avoid`, if included, fully replace the existing set (delete + recreate) — not merged/diffed. Omit them to leave meals/foods untouched while updating other fields.",
        examples=[OpenApiExample("Request — notes only", value={"notes": "Reduce salt intake — mild swelling noted."}, request_only=True)],
    ),
    destroy=extend_schema(tags=[TAG], summary="Delete a diet plan (doctor/admin only)"),
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

    @extend_schema(
        tags=[TAG],
        summary="Get the current active diet plan",
        description="Patient: their own active plan (no query params). Doctor/Admin: `?patient_id=<id>` (doctor must be assigned). 404 if the patient has no active plan.",
        responses={200: DietPlanSerializer, 404: DetailResponseSerializer},
        examples=[
            OpenApiExample("200 OK", value=_DIET_PLAN_RESPONSE_EXAMPLE, response_only=True, status_codes=["200"]),
            OpenApiExample("404 No active plan", value={"detail": "No active diet plan found.", "errors": None}, response_only=True, status_codes=["404"]),
        ],
    )
    @action(detail=False, methods=["get"])
    def active(self, request):
        patient = resolve_patient_from_request(request)
        plan = DietPlan.objects.filter(patient=patient, is_active=True).first()
        if not plan:
            return Response({"detail": "No active diet plan found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(DietPlanSerializer(plan).data)
