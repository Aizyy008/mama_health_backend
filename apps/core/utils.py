from django.shortcuts import get_object_or_404
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.core.constants import Role


def resolve_patient_from_request(request):
    """
    Returns the patient (role=PATIENT User) a request concerns:
    - PATIENT actor: themselves.
    - DOCTOR/ADMIN actor: the `patient_id` query param; a doctor must have a
      PatientDoctorAssignment to that patient.
    Raises DRF exceptions (400/403/404) on failure — call from a view and let
    them propagate.
    """
    from apps.accounts.models import User
    from apps.appointments.models import PatientDoctorAssignment

    user = request.user
    if user.role == Role.PATIENT:
        return user

    patient_id = request.query_params.get("patient_id")
    if not patient_id:
        raise ValidationError({"patient_id": "This query parameter is required."})
    patient = get_object_or_404(User, id=patient_id, role=Role.PATIENT)
    if user.role == Role.DOCTOR and not PatientDoctorAssignment.objects.filter(
        doctor=user, patient=patient
    ).exists():
        raise PermissionDenied("You are not assigned to this patient.")
    return patient
