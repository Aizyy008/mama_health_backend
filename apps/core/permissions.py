from rest_framework.permissions import BasePermission, SAFE_METHODS

from apps.core.constants import Role


class IsPatient(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role == Role.PATIENT)


class IsDoctor(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role == Role.DOCTOR)


class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role == Role.ADMIN)


class IsDoctorOrAdmin(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role in (Role.DOCTOR, Role.ADMIN)
        )


class IsAdminOrReadOnlyForDoctor(BasePermission):
    """Admin can write; doctor can only read. Used for doctor-facing reference/list views."""

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if request.user.role == Role.ADMIN:
            return True
        return request.user.role == Role.DOCTOR and request.method in SAFE_METHODS


class IsOwnerPatientOrAssignedDoctorOrAdmin(BasePermission):
    """
    Object-level permission for models with a `patient` FK.
    - Patient: only their own object
    - Doctor: only if a PatientDoctorAssignment exists to the object's patient
    - Admin: always
    """

    def has_object_permission(self, request, view, obj):
        user = request.user
        patient_id = getattr(obj, "patient_id", None)
        if patient_id is None:
            return False
        if user.role == Role.ADMIN:
            return True
        if user.role == Role.PATIENT:
            return patient_id == user.id
        if user.role == Role.DOCTOR:
            from apps.appointments.models import PatientDoctorAssignment

            return PatientDoctorAssignment.objects.filter(doctor=user, patient_id=patient_id).exists()
        return False
