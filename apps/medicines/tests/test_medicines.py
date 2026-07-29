import pytest
from django.urls import reverse
from rest_framework import status

from apps.accounts.tests.factories import PatientUserFactory
from apps.appointments.models import PatientDoctorAssignment
from apps.medicines.models import MedicineIntakeLog
from apps.medicines.tests.factories import MedicineReminderFactory

pytestmark = pytest.mark.django_db


class TestMedicineReminderRoleBoundaries:
    def test_patient_creates_own_reminder(self, patient_client, patient_user):
        resp = patient_client.post(
            reverse("medicine-reminder-list"),
            {"medicine_name": "Iron", "reminder_times": ["08:00", "20:00"], "times_per_day": 2},
            format="json",
        )
        assert resp.status_code == status.HTTP_201_CREATED
        assert resp.data["patient"]["id"] == patient_user.id

    def test_unassigned_doctor_cannot_create_for_patient(self, doctor_client):
        patient = PatientUserFactory()
        resp = doctor_client.post(
            reverse("medicine-reminder-list"),
            {"patient_id": patient.id, "medicine_name": "Iron"},
            format="json",
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_patient_cannot_see_others_reminders(self, patient_client, patient_user):
        MedicineReminderFactory(patient=patient_user)
        MedicineReminderFactory()
        resp = patient_client.get(reverse("medicine-reminder-list"))
        assert resp.data["count"] == 1


class TestLogIntake:
    def test_patient_logs_own_intake_as_taken(self, patient_client, patient_user):
        reminder = MedicineReminderFactory(patient=patient_user)
        resp = patient_client.post(
            reverse("medicine-reminder-log-intake", args=[reminder.id]), {"status": "taken"}, format="json"
        )
        assert resp.status_code == 201
        assert resp.data["status"] == "taken"
        assert resp.data["taken_at"] is not None

    def test_logging_skipped_has_no_taken_at(self, patient_client, patient_user):
        reminder = MedicineReminderFactory(patient=patient_user)
        resp = patient_client.post(
            reverse("medicine-reminder-log-intake", args=[reminder.id]), {"status": "skipped"}, format="json"
        )
        assert resp.status_code == 201
        assert resp.data["status"] == "skipped"
        assert resp.data["taken_at"] is None

    def test_patient_cannot_log_intake_on_another_patients_reminder(self, patient_client):
        other_reminder = MedicineReminderFactory()
        resp = patient_client.post(
            reverse("medicine-reminder-log-intake", args=[other_reminder.id]), {"status": "taken"}, format="json"
        )
        assert resp.status_code == status.HTTP_404_NOT_FOUND


class TestIntakeLogScoping:
    def test_patient_sees_only_own_intake_logs(self, patient_client, patient_user):
        mine = MedicineReminderFactory(patient=patient_user)
        MedicineIntakeLog.objects.create(reminder=mine, scheduled_for="2026-01-01T08:00:00Z", status="taken")

        others = MedicineReminderFactory()
        MedicineIntakeLog.objects.create(reminder=others, scheduled_for="2026-01-01T08:00:00Z", status="taken")

        resp = patient_client.get(reverse("medicine-intake-log-list"))
        assert resp.data["count"] == 1

    def test_assigned_doctor_sees_patients_intake_logs(self, doctor_client, doctor_user):
        patient = PatientUserFactory()
        PatientDoctorAssignment.objects.create(patient=patient, doctor=doctor_user)
        reminder = MedicineReminderFactory(patient=patient)
        MedicineIntakeLog.objects.create(reminder=reminder, scheduled_for="2026-01-01T08:00:00Z", status="taken")

        resp = doctor_client.get(reverse("medicine-intake-log-list"))
        assert resp.data["count"] == 1

    def test_unassigned_doctor_sees_no_intake_logs(self, doctor_client):
        reminder = MedicineReminderFactory()
        MedicineIntakeLog.objects.create(reminder=reminder, scheduled_for="2026-01-01T08:00:00Z", status="taken")

        resp = doctor_client.get(reverse("medicine-intake-log-list"))
        assert resp.data["count"] == 0
