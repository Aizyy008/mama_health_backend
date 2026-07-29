from datetime import date, timedelta

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from apps.accounts.tests.factories import DoctorUserFactory, PatientUserFactory
from apps.appointments.models import PatientDoctorAssignment
from apps.health.models import BabySizeReference, KickCountSession, SymptomType
from apps.health.tests.factories import (
    BloodPressureReadingFactory,
    BloodSugarReadingFactory,
    WaterIntakeEntryFactory,
)

pytestmark = pytest.mark.django_db


class TestBloodPressureRoleBoundaries:
    def test_patient_cannot_see_another_patients_readings(self, patient_client, patient_user):
        BloodPressureReadingFactory(patient=patient_user)
        BloodPressureReadingFactory()  # someone else's
        resp = patient_client.get(reverse("blood-pressure-list"))
        assert resp.data["count"] == 1

    def test_unassigned_doctor_sees_nothing(self, doctor_client):
        BloodPressureReadingFactory()
        resp = doctor_client.get(reverse("blood-pressure-list"))
        assert resp.data["count"] == 0

    def test_assigned_doctor_sees_patients_readings(self, doctor_client, doctor_user):
        patient = PatientUserFactory()
        PatientDoctorAssignment.objects.create(patient=patient, doctor=doctor_user)
        BloodPressureReadingFactory(patient=patient)
        resp = doctor_client.get(reverse("blood-pressure-list"))
        assert resp.data["count"] == 1

    def test_unassigned_doctor_cannot_create_reading_for_a_patient(self, doctor_client):
        """Regression test: create() has no object yet, so object-level
        permissions never run on POST — the assignment check must live in
        the serializer's validate(), not rely on has_object_permission."""
        patient = PatientUserFactory()
        resp = doctor_client.post(
            reverse("blood-pressure-list"),
            {"patient_id": patient.id, "systolic": 120, "diastolic": 80},
            format="json",
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_assigned_doctor_can_create_reading_for_a_patient(self, doctor_client, doctor_user):
        patient = PatientUserFactory()
        PatientDoctorAssignment.objects.create(patient=patient, doctor=doctor_user)
        resp = doctor_client.post(
            reverse("blood-pressure-list"),
            {"patient_id": patient.id, "systolic": 120, "diastolic": 80},
            format="json",
        )
        assert resp.status_code == status.HTTP_201_CREATED
        assert resp.data["patient"]["id"] == patient.id

    def test_patient_create_ignores_supplied_patient_id(self, patient_client, patient_user):
        other = PatientUserFactory()
        resp = patient_client.post(
            reverse("blood-pressure-list"),
            {"patient_id": other.id, "systolic": 110, "diastolic": 70},
            format="json",
        )
        assert resp.status_code == status.HTTP_201_CREATED
        assert resp.data["patient"]["id"] == patient_user.id

    def test_admin_can_create_reading_for_any_patient(self, admin_client):
        patient = PatientUserFactory()
        resp = admin_client.post(
            reverse("blood-pressure-list"),
            {"patient_id": patient.id, "systolic": 130, "diastolic": 85},
            format="json",
        )
        assert resp.status_code == status.HTTP_201_CREATED


class TestBloodSugarReadings:
    def test_patient_logs_own_reading(self, patient_client, patient_user):
        resp = patient_client.post(
            reverse("blood-sugar-list"),
            {"value_mg_dl": 95, "reading_context": "fasting"},
            format="json",
        )
        assert resp.status_code == status.HTTP_201_CREATED
        assert resp.data["patient"]["id"] == patient_user.id


class TestSymptomLogUpsert:
    def test_posting_twice_same_day_upserts_not_duplicates(self, patient_client, patient_user):
        # get_or_create: the health.0002 data migration already seeds a
        # standard "Nausea"/"Headache" list, so plain .create() would collide.
        nausea, _ = SymptomType.objects.get_or_create(name="Nausea")
        headache, _ = SymptomType.objects.get_or_create(name="Headache")
        today = date.today().isoformat()

        first = patient_client.post(
            reverse("symptom-log-list"),
            {"log_date": today, "symptom_ids": [nausea.id], "notes": "mild"},
            format="json",
        )
        assert first.status_code == status.HTTP_201_CREATED

        second = patient_client.post(
            reverse("symptom-log-list"),
            {"log_date": today, "symptom_ids": [nausea.id, headache.id], "notes": "worse"},
            format="json",
        )
        assert second.status_code == status.HTTP_201_CREATED

        list_resp = patient_client.get(reverse("symptom-log-list"))
        assert list_resp.data["count"] == 1
        assert list_resp.data["results"][0]["notes"] == "worse"
        assert len(list_resp.data["results"][0]["symptoms"]) == 2


class TestWaterIntakeDailyReset:
    def test_today_endpoint_aggregates_only_todays_entries(self, patient_client, patient_user):
        WaterIntakeEntryFactory(patient=patient_user, amount_ml=250, log_date=date.today())
        WaterIntakeEntryFactory(patient=patient_user, amount_ml=300, log_date=date.today())
        WaterIntakeEntryFactory(patient=patient_user, amount_ml=500, log_date=date.today() - timedelta(days=1))

        resp = patient_client.get(reverse("water-intake-today"))
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["total_ml"] == 550
        assert len(resp.data["entries"]) == 2

    def test_history_preserved_not_deleted(self, patient_client, patient_user):
        WaterIntakeEntryFactory(patient=patient_user, log_date=date.today() - timedelta(days=3))
        resp = patient_client.get(reverse("water-intake-list"))
        assert resp.data["count"] == 1

    def test_doctor_and_patient_cannot_access_others_today_total(self, doctor_client):
        resp = doctor_client.get(reverse("water-intake-today"))
        assert resp.status_code == status.HTTP_403_FORBIDDEN


class TestKickCounter:
    def test_start_tap_end_flow(self, patient_client, patient_user):
        start_resp = patient_client.post(reverse("kick-session-list"), {}, format="json")
        assert start_resp.status_code == status.HTTP_201_CREATED
        session_id = start_resp.data["id"]

        for _ in range(3):
            tap_resp = patient_client.post(reverse("kick-session-tap", args=[session_id]))
            assert tap_resp.status_code == status.HTTP_200_OK

        end_resp = patient_client.post(reverse("kick-session-end", args=[session_id]))
        assert end_resp.status_code == status.HTTP_200_OK
        assert end_resp.data["kick_count"] == 3
        assert end_resp.data["ended_at"] is not None

    def test_cannot_tap_ended_session(self, patient_client, patient_user):
        session = KickCountSession.objects.create(
            patient=patient_user, ended_at=timezone.now(), log_date=date.today()
        )
        resp = patient_client.post(reverse("kick-session-tap", args=[session.id]))
        assert resp.status_code == status.HTTP_400_BAD_REQUEST


class TestBabySizeReference:
    def test_seeded_reference_data_readable(self, patient_client):
        assert BabySizeReference.objects.count() > 0
        resp = patient_client.get(reverse("baby-size-detail", args=[20]))
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["week"] == 20


class TestPregnancyProgress:
    def test_patient_without_lmp_gets_404(self, patient_client):
        resp = patient_client.get(reverse("pregnancy-progress"))
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_patient_with_lmp_gets_computed_progress(self, patient_client, patient_user):
        patient_user.patient_profile.lmp_date = date.today() - timedelta(weeks=20)
        patient_user.patient_profile.save()
        resp = patient_client.get(reverse("pregnancy-progress"))
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["current_week"] == 20
        assert resp.data["trimester"] == 2

    def test_doctor_requires_patient_id_query_param(self, doctor_client):
        resp = doctor_client.get(reverse("pregnancy-progress"))
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_unassigned_doctor_forbidden(self, doctor_client):
        patient = PatientUserFactory()
        patient.patient_profile.lmp_date = date.today() - timedelta(weeks=10)
        patient.patient_profile.save()
        resp = doctor_client.get(reverse("pregnancy-progress"), {"patient_id": patient.id})
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_assigned_doctor_can_view(self, doctor_client, doctor_user):
        patient = PatientUserFactory()
        patient.patient_profile.lmp_date = date.today() - timedelta(weeks=10)
        patient.patient_profile.save()
        PatientDoctorAssignment.objects.create(patient=patient, doctor=doctor_user)
        resp = doctor_client.get(reverse("pregnancy-progress"), {"patient_id": patient.id})
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["current_week"] == 10
