from datetime import timedelta

from django.utils import timezone

FULL_TERM_DAYS = 280  # 40 weeks


def get_pregnancy_progress(patient_profile) -> dict | None:
    """Computed from PatientProfile.lmp_date/edd_date at read time — never
    stored, so there is no stale-percentage bug class to worry about."""
    if not patient_profile.lmp_date:
        return None

    today = timezone.now().date()
    days_pregnant = max((today - patient_profile.lmp_date).days, 0)
    current_week = days_pregnant // 7
    current_day = days_pregnant % 7
    percent_complete = round(min(days_pregnant / FULL_TERM_DAYS, 1.0) * 100, 1)
    trimester = 1 if current_week < 13 else (2 if current_week < 27 else 3)
    edd = patient_profile.edd_date or (patient_profile.lmp_date + timedelta(days=FULL_TERM_DAYS))
    days_remaining = max((edd - today).days, 0)

    return {
        "lmp_date": patient_profile.lmp_date,
        "edd_date": edd,
        "current_week": current_week,
        "current_day": current_day,
        "percent_complete": percent_complete,
        "trimester": trimester,
        "days_remaining": days_remaining,
    }
