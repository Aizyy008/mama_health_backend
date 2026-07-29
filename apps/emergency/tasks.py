from celery import shared_task

from apps.notifications import services as notification_services
from apps.notifications.adapters.factory import get_whatsapp_adapter


@shared_task
def fan_out_sos_alert(event_id):
    """
    Fans out an emergency SOS to: every doctor assigned to the patient, all
    active admins, and (best-effort, direct WhatsApp — not a Notification
    row, since the emergency contact isn't a system User) the patient's
    recorded emergency contact number.
    """
    from apps.accounts.models import User
    from apps.appointments.models import PatientDoctorAssignment
    from apps.core.constants import Role
    from apps.emergency.models import EmergencySOSEvent

    try:
        event = EmergencySOSEvent.objects.select_related("patient", "patient__patient_profile").get(
            id=event_id
        )
    except EmergencySOSEvent.DoesNotExist:
        return

    patient = event.patient
    patient_label = patient.get_full_name() or patient.email
    location = (
        f" Location: {event.latitude}, {event.longitude}."
        if event.latitude is not None and event.longitude is not None
        else " No location was shared."
    )
    body = f"{patient_label} has triggered an emergency SOS.{location}"

    doctor_ids = PatientDoctorAssignment.objects.filter(patient=patient).values_list("doctor_id", flat=True)
    recipients = list(User.objects.filter(id__in=doctor_ids)) + list(
        User.objects.filter(role=Role.ADMIN, is_active=True)
    )
    for recipient in recipients:
        notification_services.notify(
            recipient=recipient,
            notification_type="emergency",
            title="Emergency SOS",
            body=body,
            data={"sos_event_id": event.id},
            channels=["push", "whatsapp"],
        )

    profile = getattr(patient, "patient_profile", None)
    if profile and profile.emergency_contact_phone:
        get_whatsapp_adapter().send_message(profile.emergency_contact_phone, "Emergency SOS", body)
