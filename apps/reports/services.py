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
    today = now.date()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    week_ago = now - timedelta(days=7)

    return {
        "total_patients": User.objects.filter(role=Role.PATIENT).count(),
        "total_doctors": User.objects.filter(role=Role.DOCTOR).count(),
        "total_appointments": Appointment.objects.count(),
        "appointments_this_month": Appointment.objects.filter(scheduled_at__gte=month_start).count(),
        "today_appointments": Appointment.objects.filter(scheduled_at__date=today).count(),
        "active_sos_events": EmergencySOSEvent.objects.filter(status=EmergencySOSEvent.Status.ACTIVE).count(),
        "new_patients_this_week": User.objects.filter(role=Role.PATIENT, date_joined__gte=week_ago).count(),
        "trimester_distribution": _build_trimester_distribution(),
        "recent_activities": build_recent_activities(),
    }


def _build_trimester_distribution() -> dict:
    from apps.accounts.models import PatientProfile

    distribution = {"trimester_1": 0, "trimester_2": 0, "trimester_3": 0, "unknown": 0}
    for profile in PatientProfile.objects.filter(lmp_date__isnull=False).only("lmp_date", "edd_date"):
        progress = get_pregnancy_progress(profile)
        distribution[f"trimester_{progress['trimester']}"] += 1
    total_patients = PatientProfile.objects.count()
    distribution["unknown"] = total_patients - sum(
        v for k, v in distribution.items() if k != "unknown"
    )
    return distribution


def build_recent_activities(limit: int = 15) -> list[dict]:
    """
    A lightweight, computed-on-read activity feed for the admin dashboard —
    no Activity model/table, just the most recent rows from a few key
    models merged and sorted, mirroring this project's existing
    "computed, not stored" approach (see pregnancy progress).
    """
    from apps.accounts.models import User
    from apps.core.constants import Role
    from apps.emergency.models import EmergencySOSEvent

    events = []

    for patient in User.objects.filter(role=Role.PATIENT).order_by("-date_joined")[:limit]:
        events.append(
            {
                "type": "patient_registered",
                "description": f"{patient.get_full_name() or patient.email} registered as a patient.",
                "timestamp": patient.date_joined,
            }
        )

    for appointment in Appointment.objects.select_related("patient", "doctor").order_by("-created_at")[:limit]:
        patient_label = appointment.patient.get_full_name() or appointment.patient.email
        doctor_label = appointment.doctor.get_full_name() or appointment.doctor.email
        events.append(
            {
                "type": "appointment_booked",
                "description": f"{patient_label} booked an appointment with {doctor_label}.",
                "timestamp": appointment.created_at,
            }
        )

    for sos in EmergencySOSEvent.objects.select_related("patient").order_by("-created_at")[:limit]:
        patient_label = sos.patient.get_full_name() or sos.patient.email
        events.append(
            {
                "type": "sos_triggered",
                "description": f"{patient_label} triggered an emergency SOS.",
                "timestamp": sos.created_at,
            }
        )

    events.sort(key=lambda e: e["timestamp"], reverse=True)
    return events[:limit]


def search(query: str) -> dict:
    """
    Simple icontains search across doctors/patients/appointments for the
    admin dashboard's global search — no full-text search infra (no
    Elasticsearch/pg trigram), matching this project's otherwise-minimal
    infra footprint. Each category capped at 10 results.
    """
    from django.db.models import Q

    from apps.accounts.models import User
    from apps.core.constants import Role

    name_match = Q(first_name__icontains=query) | Q(last_name__icontains=query) | Q(email__icontains=query)

    doctors = User.objects.filter(role=Role.DOCTOR).filter(name_match).select_related("doctor_profile")[:10]
    patients = User.objects.filter(role=Role.PATIENT).filter(name_match).select_related("patient_profile")[:10]
    appointments = (
        Appointment.objects.select_related("patient", "doctor")
        .filter(
            Q(patient__first_name__icontains=query)
            | Q(patient__last_name__icontains=query)
            | Q(patient__email__icontains=query)
            | Q(doctor__first_name__icontains=query)
            | Q(doctor__last_name__icontains=query)
            | Q(doctor__email__icontains=query)
            | Q(reason__icontains=query)
        )
        .order_by("-scheduled_at")[:10]
    )

    return {"doctors": doctors, "patients": patients, "appointments": appointments}
