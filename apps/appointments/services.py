from django.db import transaction
from django.utils import timezone

from apps.appointments.models import Appointment, DoctorRating, PatientDoctorAssignment
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


_TERMINAL_STATUSES = {Appointment.Status.COMPLETED, Appointment.Status.CANCELLED, Appointment.Status.NO_SHOW}


def reschedule_appointment(*, appointment: Appointment, actor, scheduled_at, duration_minutes=None):
    if appointment.status in _TERMINAL_STATUSES:
        raise ValueError(f"Cannot reschedule a {appointment.get_status_display().lower()} appointment.")

    appointment.scheduled_at = scheduled_at
    update_fields = ["scheduled_at", "updated_at"]
    if duration_minutes is not None:
        appointment.duration_minutes = duration_minutes
        update_fields.append("duration_minutes")
    appointment.save(update_fields=update_fields)

    from apps.notifications import services as notification_services

    if actor.id == appointment.patient_id:
        recipients = [appointment.doctor]
    elif actor.id == appointment.doctor_id:
        recipients = [appointment.patient]
    else:
        recipients = [appointment.patient, appointment.doctor]

    when = timezone.localtime(appointment.scheduled_at).strftime("%b %d, %H:%M")
    for recipient in recipients:
        channels = ["push", "whatsapp"] if recipient.role == Role.DOCTOR else ["push"]
        notification_services.notify(
            recipient=recipient,
            notification_type="appointment",
            title="Appointment rescheduled",
            body=f"Your appointment has been rescheduled to {when}.",
            data={"appointment_id": appointment.id},
            channels=channels,
        )
    return appointment


def rate_appointment(*, appointment: Appointment, score: int, comment: str = "") -> DoctorRating:
    if appointment.status != Appointment.Status.COMPLETED:
        raise ValueError("Only completed appointments can be rated.")
    if DoctorRating.objects.filter(appointment=appointment).exists():
        raise ValueError("This appointment has already been rated.")
    return DoctorRating.objects.create(
        appointment=appointment,
        patient=appointment.patient,
        doctor=appointment.doctor,
        score=score,
        comment=comment,
    )


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
