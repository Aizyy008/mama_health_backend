from datetime import timedelta

from django.utils import timezone

from apps.appointments.models import Appointment
from apps.diet.models import DietPlan
from apps.health.models import BloodPressureReading, BloodSugarReading, SymptomLog
from apps.health.services import get_pregnancy_progress
from apps.medicines.models import MedicineIntakeLog


def build_patient_summary(patient) -> dict:
    profile = getattr(patient, "patient_profile", None)
    pregnancy_progress = get_pregnancy_progress(profile) if profile else None

    latest_blood_pressure = BloodPressureReading.objects.filter(patient=patient).order_by("-recorded_at").first()
    latest_blood_sugar = BloodSugarReading.objects.filter(patient=patient).order_by("-recorded_at").first()
    active_diet_plan = DietPlan.objects.filter(patient=patient, is_active=True).first()

    upcoming_appointments = Appointment.objects.filter(
        patient=patient,
        status__in=[Appointment.Status.PENDING, Appointment.Status.CONFIRMED],
        scheduled_at__gte=timezone.now(),
    ).select_related("doctor")[:5]

    recent_symptoms = SymptomLog.objects.filter(
        patient=patient, log_date__gte=timezone.now().date() - timedelta(days=7)
    ).prefetch_related("symptoms")

    week_ago = timezone.now() - timedelta(days=7)
    recent_intake_logs = MedicineIntakeLog.objects.filter(reminder__patient=patient, scheduled_for__gte=week_ago)
    medicine_adherence = {
        "taken": recent_intake_logs.filter(status=MedicineIntakeLog.Status.TAKEN).count(),
        "skipped": recent_intake_logs.filter(status=MedicineIntakeLog.Status.SKIPPED).count(),
        "pending": recent_intake_logs.filter(status=MedicineIntakeLog.Status.PENDING).count(),
    }

    return {
        "pregnancy_progress": pregnancy_progress,
        "latest_blood_pressure": latest_blood_pressure,
        "latest_blood_sugar": latest_blood_sugar,
        "active_diet_plan": active_diet_plan,
        "upcoming_appointments": upcoming_appointments,
        "recent_symptoms": recent_symptoms,
        "medicine_adherence": medicine_adherence,
    }


def build_admin_stats() -> dict:
    from apps.accounts.models import User
    from apps.core.constants import Role
    from apps.emergency.models import EmergencySOSEvent

    now = timezone.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    week_ago = now - timedelta(days=7)

    return {
        "total_patients": User.objects.filter(role=Role.PATIENT).count(),
        "total_doctors": User.objects.filter(role=Role.DOCTOR).count(),
        "total_appointments": Appointment.objects.count(),
        "appointments_this_month": Appointment.objects.filter(scheduled_at__gte=month_start).count(),
        "active_sos_events": EmergencySOSEvent.objects.filter(status=EmergencySOSEvent.Status.ACTIVE).count(),
        "new_patients_this_week": User.objects.filter(role=Role.PATIENT, date_joined__gte=week_ago).count(),
    }
