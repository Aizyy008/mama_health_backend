from rest_framework.permissions import BasePermission

from apps.core.constants import Role


class IsAppointmentParticipantOrAdmin(BasePermission):
    """
    Object-level permission for Appointment. Deliberately NOT the generic
    core.permissions.IsOwnerPatientOrAssignedDoctorOrAdmin: an appointment has
    TWO parties (a specific patient AND a specific doctor), so "doctor is
    assigned to this patient" is not sufficient — a different doctor could
    also be assigned to the same patient via another appointment and must
    not see this one. Only the exact doctor/patient on the object (or admin)
    may access it.
    """

    def has_object_permission(self, request, view, obj):
        user = request.user
        if user.role == Role.ADMIN:
            return True
        if user.role == Role.PATIENT:
            return obj.patient_id == user.id
        if user.role == Role.DOCTOR:
            return obj.doctor_id == user.id
        return False
