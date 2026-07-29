from django.db.models import Sum
from django.utils import timezone
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import generics, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.permissions import IsOwnerPatientOrAssignedDoctorOrAdmin, IsPatient
from apps.core.utils import resolve_patient_from_request
from apps.core.viewsets import PatientOwnedCreateMixin, PatientScopedQuerysetMixin
from apps.health import services
from apps.health.models import BabySizeReference, BloodPressureReading, BloodSugarReading, KickCountSession, KickEvent, SymptomLog, WaterIntakeEntry
from apps.health.serializers import (
    BabySizeReferenceSerializer,
    BloodPressureReadingSerializer,
    BloodSugarReadingSerializer,
    KickCountSessionSerializer,
    PregnancyProgressSerializer,
    SymptomLogSerializer,
    WaterIntakeEntrySerializer,
)

TAG = "Health"


@extend_schema_view(
    list=extend_schema(tags=[TAG]),
    retrieve=extend_schema(tags=[TAG]),
    create=extend_schema(tags=[TAG]),
    update=extend_schema(tags=[TAG]),
    partial_update=extend_schema(tags=[TAG]),
    destroy=extend_schema(tags=[TAG]),
)
class BloodPressureReadingViewSet(PatientScopedQuerysetMixin, PatientOwnedCreateMixin, viewsets.ModelViewSet):
    serializer_class = BloodPressureReadingSerializer
    queryset = BloodPressureReading.objects.select_related("patient")
    permission_classes = [permissions.IsAuthenticated, IsOwnerPatientOrAssignedDoctorOrAdmin]


@extend_schema_view(
    list=extend_schema(tags=[TAG]),
    retrieve=extend_schema(tags=[TAG]),
    create=extend_schema(tags=[TAG]),
    update=extend_schema(tags=[TAG]),
    partial_update=extend_schema(tags=[TAG]),
    destroy=extend_schema(tags=[TAG]),
)
class BloodSugarReadingViewSet(PatientScopedQuerysetMixin, PatientOwnedCreateMixin, viewsets.ModelViewSet):
    serializer_class = BloodSugarReadingSerializer
    queryset = BloodSugarReading.objects.select_related("patient")
    permission_classes = [permissions.IsAuthenticated, IsOwnerPatientOrAssignedDoctorOrAdmin]


@extend_schema_view(
    list=extend_schema(tags=[TAG]),
    retrieve=extend_schema(tags=[TAG]),
    create=extend_schema(tags=[TAG]),
    update=extend_schema(tags=[TAG]),
    partial_update=extend_schema(tags=[TAG]),
    destroy=extend_schema(tags=[TAG]),
)
class SymptomLogViewSet(PatientScopedQuerysetMixin, PatientOwnedCreateMixin, viewsets.ModelViewSet):
    """POST upserts by (patient, log_date) — one entry per day, see SymptomLogSerializer.create()."""

    serializer_class = SymptomLogSerializer
    queryset = SymptomLog.objects.select_related("patient").prefetch_related("symptoms")
    permission_classes = [permissions.IsAuthenticated, IsOwnerPatientOrAssignedDoctorOrAdmin]


@extend_schema_view(
    list=extend_schema(tags=[TAG]),
    retrieve=extend_schema(tags=[TAG]),
    create=extend_schema(tags=[TAG]),
)
class WaterIntakeEntryViewSet(PatientScopedQuerysetMixin, PatientOwnedCreateMixin, viewsets.ModelViewSet):
    """No update/delete — water intake is an append-only log; 'today' is a query-time filter, not a reset."""

    serializer_class = WaterIntakeEntrySerializer
    queryset = WaterIntakeEntry.objects.select_related("patient")
    permission_classes = [permissions.IsAuthenticated, IsOwnerPatientOrAssignedDoctorOrAdmin]
    http_method_names = ["get", "post", "head", "options"]

    @extend_schema(tags=[TAG])
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


@extend_schema_view(
    list=extend_schema(tags=[TAG]),
    retrieve=extend_schema(tags=[TAG]),
    create=extend_schema(tags=[TAG]),
)
class KickCountSessionViewSet(PatientScopedQuerysetMixin, PatientOwnedCreateMixin, viewsets.ModelViewSet):
    serializer_class = KickCountSessionSerializer
    queryset = KickCountSession.objects.select_related("patient").prefetch_related("events")
    permission_classes = [permissions.IsAuthenticated, IsOwnerPatientOrAssignedDoctorOrAdmin]
    http_method_names = ["get", "post", "head", "options"]

    @extend_schema(tags=[TAG])
    @action(detail=True, methods=["post"])
    def tap(self, request, pk=None):
        session = self.get_object()
        if session.ended_at:
            return Response({"detail": "This session has already ended."}, status=status.HTTP_400_BAD_REQUEST)
        KickEvent.objects.create(session=session)
        session.kick_count += 1
        session.save(update_fields=["kick_count"])
        return Response(KickCountSessionSerializer(session).data)

    @extend_schema(tags=[TAG])
    @action(detail=True, methods=["post"])
    def end(self, request, pk=None):
        session = self.get_object()
        session.ended_at = timezone.now()
        session.save(update_fields=["ended_at"])
        return Response(KickCountSessionSerializer(session).data)


@extend_schema_view(
    list=extend_schema(tags=[TAG]),
    retrieve=extend_schema(tags=[TAG]),
)
class BabySizeReferenceViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = BabySizeReferenceSerializer
    queryset = BabySizeReference.objects.all()
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = "week"
    pagination_class = None


@extend_schema(tags=[TAG])
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
