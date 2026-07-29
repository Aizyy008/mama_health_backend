from apps.emergency.models import EmergencySOSEvent


def trigger_sos(*, patient, latitude=None, longitude=None, notes=""):
    event = EmergencySOSEvent.objects.create(
        patient=patient, latitude=latitude, longitude=longitude, notes=notes
    )
    from apps.emergency.tasks import fan_out_sos_alert

    fan_out_sos_alert.delay(event.id)
    return event
