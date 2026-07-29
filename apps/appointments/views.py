from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.appointments import services
from apps.appointments.models import Appointment
from apps.appointments.permissions import IsAppointmentParticipantOrAdmin
from apps.appointments.serializers import (
    AppointmentDoctorNotesSerializer,
    AppointmentSerializer,
    AppointmentStatusUpdateSerializer,
)
from apps.core.constants import Role
from apps.core.permissions import IsDoctorOrAdmin


@extend_schema_view(
    list=extend_schema(tags=["Appointments"]),
    retrieve=extend_schema(tags=["Appointments"]),
    create=extend_schema(tags=["Appointments"]),
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
    permission_classes = [permissions.IsAuthenticated, IsAppointmentParticipantOrAdmin]

    def get_queryset(self):
        qs = Appointment.objects.select_related("patient", "doctor")
        user = self.request.user
        if user.role == Role.PATIENT:
            return qs.filter(patient=user)
        if user.role == Role.DOCTOR:
            return qs.filter(doctor=user)
        return qs

    def perform_create(self, serializer):
        user = self.request.user
        if user.role == Role.PATIENT:
            serializer.save(patient=user)
        else:
            serializer.save()

    @extend_schema(tags=["Appointments"], request=AppointmentStatusUpdateSerializer)
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

    @extend_schema(tags=["Appointments"], request=AppointmentDoctorNotesSerializer)
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
