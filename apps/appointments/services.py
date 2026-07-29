from django.db import transaction
from django.utils import timezone

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
        raise ValueError("Please select a valid doctor to book with.")
    if patient.role != Role.PATIENT:
        raise ValueError("Please select a valid patient for this appointment.")

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

    from apps.notifications import services as notification_services

    patient_label = patient.get_full_name() or patient.email
    when = timezone.localtime(appointment.scheduled_at).strftime("%b %d, %H:%M")
    notification_services.notify(
        recipient=doctor,
        notification_type="appointment",
        title="New appointment booked",
        body=f"{patient_label} booked an appointment with you on {when}.",
        data={"appointment_id": appointment.id},
        channels=["push", "whatsapp"],
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
    _notify_status_change(appointment=appointment, actor=actor)
    return appointment


def _notify_status_change(*, appointment: Appointment, actor):
    from apps.notifications import services as notification_services

    if actor.id == appointment.patient_id:
        recipients = [appointment.doctor]
    elif actor.id == appointment.doctor_id:
        recipients = [appointment.patient]
    else:  # admin (or another system actor) changed it — notify both parties
        recipients = [appointment.patient, appointment.doctor]

    status_label = appointment.get_status_display().lower()
    when = timezone.localtime(appointment.scheduled_at).strftime("%b %d, %H:%M")
    for recipient in recipients:
        channels = ["push", "whatsapp"] if recipient.role == Role.DOCTOR else ["push"]
        notification_services.notify(
            recipient=recipient,
            notification_type="appointment",
            title="Appointment update",
            body=f"Your appointment on {when} is now {status_label}.",
            data={"appointment_id": appointment.id, "status": appointment.status},
            channels=channels,
        )
