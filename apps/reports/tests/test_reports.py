from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from apps.accounts.tests.factories import DoctorUserFactory, PatientUserFactory
from apps.appointments.models import PatientDoctorAssignment
from apps.appointments.tests.factories import AppointmentFactory
from apps.diet.tests.factories import DietPlanFactory
from apps.health.tests.factories import BloodPressureReadingFactory

pytestmark = pytest.mark.django_db


class TestPatientSummaryReport:
    def test_patient_sees_own_summary(self, patient_client, patient_user):
        BloodPressureReadingFactory(patient=patient_user, systolic=118, diastolic=76)
        DietPlanFactory(patient=patient_user, is_active=True)
        AppointmentFactory(
            patient=patient_user, status="confirmed", scheduled_at=timezone.now() + timedelta(days=1)
        )

        resp = patient_client.get(reverse("report-patient-summary"))
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["latest_blood_pressure"]["systolic"] == 118
        assert resp.data["active_diet_plan"] is not None
        assert len(resp.data["upcoming_appointments"]) == 1

    def test_summary_handles_patient_with_no_data_gracefully(self, patient_client):
        resp = patient_client.get(reverse("report-patient-summary"))
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["pregnancy_progress"] is None
        assert resp.data["latest_blood_pressure"] is None
        assert resp.data["active_diet_plan"] is None
        assert resp.data["upcoming_appointments"] == []
        assert resp.data["medicine_adherence"] == {"taken": 0, "skipped": 0, "pending": 0}

    def test_doctor_requires_patient_id(self, doctor_client):
        resp = doctor_client.get(reverse("report-patient-summary"))
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_unassigned_doctor_forbidden(self, doctor_client):
        patient = PatientUserFactory()
        resp = doctor_client.get(reverse("report-patient-summary"), {"patient_id": patient.id})
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_assigned_doctor_can_view_summary(self, doctor_client, doctor_user):
        patient = PatientUserFactory()
        PatientDoctorAssignment.objects.create(patient=patient, doctor=doctor_user)
        BloodPressureReadingFactory(patient=patient)
        resp = doctor_client.get(reverse("report-patient-summary"), {"patient_id": patient.id})
        assert resp.status_code == status.HTTP_200_OK

    def test_admin_can_view_any_patient_summary(self, admin_client):
        patient = PatientUserFactory()
        resp = admin_client.get(reverse("report-patient-summary"), {"patient_id": patient.id})
        assert resp.status_code == status.HTTP_200_OK


class TestAdminStats:
    def test_only_admin_can_view_stats(self, patient_client, doctor_client, admin_client):
        assert patient_client.get(reverse("report-admin-stats")).status_code == status.HTTP_403_FORBIDDEN
        assert doctor_client.get(reverse("report-admin-stats")).status_code == status.HTTP_403_FORBIDDEN
        assert admin_client.get(reverse("report-admin-stats")).status_code == status.HTTP_200_OK

    def test_stats_reflect_actual_counts(self, admin_client):
        p1, p2 = PatientUserFactory(), PatientUserFactory()
        doctor = DoctorUserFactory()
        AppointmentFactory(patient=p1, doctor=doctor)  # reuse existing users — don't implicitly create more

        resp = admin_client.get(reverse("report-admin-stats"))
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["total_patients"] == 2
        assert resp.data["total_doctors"] == 1
        assert resp.data["total_appointments"] == 1
