from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"
    verbose_name = "Core"

    def ready(self):
        # Several models share a "status" field name with distinct choice
        # sets, which drf-spectacular can't disambiguate on its own — it
        # falls back to an auto-generated name (e.g. "Status1d1Enum") and
        # warns. Registering explicit names here (all app models are loaded
        # by the time ready() runs, unlike at settings-module import time)
        # gives each a clean, stable name in the generated Swagger schema.
        from django.conf import settings

        from apps.accounts.models import DoctorInvite
        from apps.appointments.models import Appointment
        from apps.emergency.models import EmergencySOSEvent
        from apps.medicines.models import MedicineIntakeLog

        settings.SPECTACULAR_SETTINGS.setdefault("ENUM_NAME_OVERRIDES", {}).update(
            {
                "AppointmentStatusEnum": Appointment.Status.choices,
                "MedicineIntakeStatusEnum": MedicineIntakeLog.Status.choices,
                "DoctorInviteStatusEnum": DoctorInvite.Status.choices,
                "EmergencySOSStatusEnum": EmergencySOSEvent.Status.choices,
            }
        )
