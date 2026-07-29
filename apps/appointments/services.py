from django.db import transaction

from apps.appointments.models import Appointment, PatientDoctorAssignment
from apps.core.constants import Role

ALLOWED_TRANSITIONS = {
    Appointment.Status.PENDING: {Appointment.Status.CONFIRMED, Appointment.Status.CANCELLED},
    Appointment.Status.CONFIRMED: {
        Appointment.Status.COMPLETED,
        Appointment.Status.CANCELLED,
        Appointment.Status.NO_SHOW,
    },
    Appointment.Status.COMPLETED: set(),
    Appointment.Status.CANCELLED: set(),
    Appointment.Status.NO_SHOW: set(),
}


@transaction.atomic
def book_appointment(*, patient, doctor, appointment_type, scheduled_at, duration_minutes=30, reason=""):
    if doctor.role != Role.DOCTOR:
        raise ValueError("Selected user is not a doctor.")
    if patient.role != Role.PATIENT:
        raise ValueError("Selected user is not a patient.")

    appointment = Appointment.objects.create(
        patient=patient,
        doctor=doctor,
        appointment_type=appointment_type,
        scheduled_at=scheduled_at,
        duration_minutes=duration_minutes,
        reason=reason,
    )

    has_existing_assignment = PatientDoctorAssignment.objects.filter(patient=patient).exists()
    PatientDoctorAssignment.objects.get_or_create(
        patient=patient,
        doctor=doctor,
        defaults={"is_primary": not has_existing_assignment},
    )
    return appointment


def transition_status(*, appointment: Appointment, new_status: str, actor, cancellation_reason: str = ""):
    allowed = ALLOWED_TRANSITIONS.get(appointment.status, set())
    if new_status not in allowed:
        raise ValueError(f"Cannot move an appointment from '{appointment.status}' to '{new_status}'.")

    appointment.status = new_status
    if new_status == Appointment.Status.CANCELLED:
        appointment.cancelled_by = actor
        appointment.cancellation_reason = cancellation_reason
    appointment.save(update_fields=["status", "cancelled_by", "cancellation_reason", "updated_at"])
    return appointment
