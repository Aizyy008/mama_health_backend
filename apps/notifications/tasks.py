from datetime import datetime, timedelta

from celery import shared_task
from django.db.models import Q
from django.utils import timezone

from apps.notifications import services

REMINDER_WINDOW_MINUTES = 60


@shared_task
def send_appointment_reminders():
    """Notifies both parties of appointments starting within the next hour
    that haven't been reminded yet. Patient gets push; doctor additionally
    gets WhatsApp, per the doc's 'doctor receives appointment notifications
    via WhatsApp' requirement."""
    from apps.appointments.models import Appointment

    now = timezone.now()
    window_end = now + timedelta(minutes=REMINDER_WINDOW_MINUTES)
    due = Appointment.objects.filter(
        status__in=[Appointment.Status.PENDING, Appointment.Status.CONFIRMED],
        scheduled_at__gte=now,
        scheduled_at__lte=window_end,
        reminder_sent_at__isnull=True,
    ).select_related("patient", "doctor")

    for appointment in due:
        doctor_label = appointment.doctor.get_full_name() or appointment.doctor.email
        patient_label = appointment.patient.get_full_name() or appointment.patient.email
        when = timezone.localtime(appointment.scheduled_at).strftime("%H:%M")

        services.notify(
            recipient=appointment.patient,
            notification_type="appointment",
            title="Upcoming appointment",
            body=f"You have an appointment with Dr. {doctor_label} at {when}.",
            data={"appointment_id": appointment.id},
            channels=["push"],
        )
        services.notify(
            recipient=appointment.doctor,
            notification_type="appointment",
            title="Upcoming appointment",
            body=f"You have an appointment with {patient_label} at {when}.",
            data={"appointment_id": appointment.id},
            channels=["push", "whatsapp"],
        )
        appointment.reminder_sent_at = now
        appointment.save(update_fields=["reminder_sent_at"])


@shared_task
def send_medicine_reminders():
    """Scans active MedicineReminder rows for a reminder_time falling in the
    current +/-5 minute window and, if not already logged for that exact
    scheduled_for timestamp, creates a pending MedicineIntakeLog + notifies."""
    from apps.medicines.models import MedicineIntakeLog, MedicineReminder

    now = timezone.now()
    today = timezone.localdate()
    window_start = (now - timedelta(minutes=5)).strftime("%H:%M")
    window_end = (now + timedelta(minutes=5)).strftime("%H:%M")

    active_reminders = MedicineReminder.objects.filter(is_active=True, start_date__lte=today).filter(
        Q(end_date__isnull=True) | Q(end_date__gte=today)
    )

    for reminder in active_reminders:
        for time_str in reminder.reminder_times:
            if not (window_start <= time_str <= window_end):
                continue
            hour, minute = map(int, time_str.split(":"))
            scheduled_for = timezone.make_aware(
                datetime.combine(today, datetime.min.time().replace(hour=hour, minute=minute))
            )
            if MedicineIntakeLog.objects.filter(reminder=reminder, scheduled_for=scheduled_for).exists():
                continue

            MedicineIntakeLog.objects.create(
                reminder=reminder, scheduled_for=scheduled_for, status=MedicineIntakeLog.Status.PENDING
            )
            services.notify(
                recipient=reminder.patient,
                notification_type="medicine",
                title="Medicine reminder",
                body=f"Time to take {reminder.medicine_name} ({reminder.dosage}).".strip(),
                data={"reminder_id": reminder.id},
                channels=["push"],
            )


@shared_task
def send_weekly_pregnancy_update():
    """Runs daily; only actually notifies patients whose pregnancy-week just
    incremented (days_pregnant is an exact multiple of 7), so it's safe to
    run once a day without extra state tracking."""
    from apps.accounts.models import PatientProfile
    from apps.health.services import get_pregnancy_progress

    today = timezone.now().date()
    profiles = PatientProfile.objects.filter(lmp_date__isnull=False).select_related("user")

    for profile in profiles:
        days_pregnant = (today - profile.lmp_date).days
        if days_pregnant <= 0 or days_pregnant % 7 != 0:
            continue
        progress = get_pregnancy_progress(profile)
        if progress is None:
            continue
        services.notify(
            recipient=profile.user,
            notification_type="weekly_update",
            title=f"Week {progress['current_week']} of your pregnancy",
            body=(
                f"You're {progress['percent_complete']}% through your pregnancy — "
                f"about {progress['days_remaining']} days to go!"
            ),
            data={"week": progress["current_week"]},
            channels=["push"],
        )


@shared_task
def broadcast_notification(*, title, body, target_role=None):
    """Fans out an admin broadcast asynchronously so the HTTP request that
    triggered it returns immediately rather than blocking on every user's
    push dispatch."""
    from apps.accounts.models import User
    from apps.core.constants import Role

    roles = [target_role] if target_role else [Role.PATIENT, Role.DOCTOR]
    recipients = User.objects.filter(role__in=roles, is_active=True)
    for recipient in recipients:
        services.notify(
            recipient=recipient,
            notification_type="broadcast",
            title=title,
            body=body,
            channels=["push"],
        )


@shared_task
def cleanup_expired_invites_and_tokens():
    from apps.accounts.models import DoctorInvite, EmailVerificationToken, PasswordResetToken

    now = timezone.now()
    DoctorInvite.objects.filter(status=DoctorInvite.Status.PENDING, expires_at__lt=now).update(
        status=DoctorInvite.Status.EXPIRED
    )
    EmailVerificationToken.objects.filter(used_at__isnull=True, expires_at__lt=now).delete()
    PasswordResetToken.objects.filter(used_at__isnull=True, expires_at__lt=now).delete()
