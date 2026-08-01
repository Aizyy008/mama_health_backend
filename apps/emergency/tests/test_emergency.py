from unittest.mock import patch

import pytest
from django.urls import reverse
from rest_framework import status

from apps.accounts.tests.factories import AdminUserFactory, DoctorUserFactory, PatientUserFactory
from apps.appointments.models import PatientDoctorAssignment
from apps.emergency.models import EmergencySOSEvent
from apps.notifications.models import Notification

pytestmark = pytest.mark.django_db


class TestTriggerSOS:
    def test_only_patient_can_trigger_sos(self, patient_client, doctor_client, admin_client):
        payload = {"latitude": 24.86, "longitude": 67.01, "notes": "Severe pain"}
        assert patient_client.post(reverse("emergency-sos-list"), payload, format="json").status_code == status.HTTP_201_CREATED
        assert doctor_client.post(reverse("emergency-sos-list"), payload, format="json").status_code == status.HTTP_403_FORBIDDEN
        assert admin_client.post(reverse("emergency-sos-list"), payload, format="json").status_code == status.HTTP_403_FORBIDDEN

    def test_event_defaults_to_active(self, patient_client, patient_user):
        resp = patient_client.post(reverse("emergency-sos-list"), {}, format="json")
        assert resp.status_code == status.HTTP_201_CREATED
        assert resp.data["status"] == "active"
        assert resp.data["patient"]["id"] == patient_user.id


class TestFanOut:
    def test_notifies_assigned_doctors_and_all_admins(self, patient_client, patient_user):
        assigned_doctor = DoctorUserFactory()
        unrelated_doctor = DoctorUserFactory()
        PatientDoctorAssignment.objects.create(patient=patient_user, doctor=assigned_doctor)
        admin = AdminUserFactory()

        resp = patient_client.post(
            reverse("emergency-sos-list"), {"latitude": 24.86, "longitude": 67.01}, format="json"
        )
        assert resp.status_code == status.HTTP_201_CREATED

        assert Notification.objects.filter(recipient=assigned_doctor, notification_type="emergency").exists()
        assert Notification.objects.filter(recipient=admin, notification_type="emergency").exists()
        assert not Notification.objects.filter(recipient=unrelated_doctor, notification_type="emergency").exists()

    def test_notifies_emergency_contact_via_whatsapp(self, patient_client, patient_user):
        patient_user.patient_profile.emergency_contact_phone = "+15551234567"
        patient_user.patient_profile.save()

        with patch("apps.emergency.tasks.get_whatsapp_adapter") as mock_factory:
            patient_client.post(
                reverse("emergency-sos-list"), {"latitude": 24.86, "longitude": 67.01}, format="json"
            )
        mock_factory.return_value.send_message.assert_called_once()
        args = mock_factory.return_value.send_message.call_args[0]
        assert args[0] == "+15551234567"


class TestReadScoping:
    def test_patient_sees_only_own_events(self, patient_client, patient_user):
        EmergencySOSEvent.objects.create(patient=patient_user)
        EmergencySOSEvent.objects.create(patient=PatientUserFactory())
        resp = patient_client.get(reverse("emergency-sos-list"))
        assert resp.data["count"] == 1

    def test_unassigned_doctor_sees_nothing(self, doctor_client):
        EmergencySOSEvent.objects.create(patient=PatientUserFactory())
        resp = doctor_client.get(reverse("emergency-sos-list"))
        assert resp.data["count"] == 0

    def test_assigned_doctor_sees_patients_events(self, doctor_client, doctor_user):
        patient = PatientUserFactory()
        PatientDoctorAssignment.objects.create(patient=patient, doctor=doctor_user)
        EmergencySOSEvent.objects.create(patient=patient)
        resp = doctor_client.get(reverse("emergency-sos-list"))
        assert resp.data["count"] == 1

    def test_admin_can_filter_by_status_active(self, admin_client):
        active = EmergencySOSEvent.objects.create(patient=PatientUserFactory(), status=EmergencySOSEvent.Status.ACTIVE)
        EmergencySOSEvent.objects.create(patient=PatientUserFactory(), status=EmergencySOSEvent.Status.RESOLVED)
        resp = admin_client.get(reverse("emergency-sos-list"), {"status": "active"})
        assert resp.status_code == status.HTTP_200_OK
        returned_ids = {row["id"] for row in resp.data["results"]}
        assert returned_ids == {active.id}

    def test_admin_can_filter_by_patient_id(self, admin_client, patient_user):
        EmergencySOSEvent.objects.create(patient=patient_user)
        EmergencySOSEvent.objects.create(patient=PatientUserFactory())
        resp = admin_client.get(reverse("emergency-sos-list"), {"patient_id": patient_user.id})
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["count"] == 1


class TestResolve:
    def test_patient_can_resolve_own_event_as_false_alarm(self, patient_client, patient_user):
        event = EmergencySOSEvent.objects.create(patient=patient_user)
        resp = patient_client.post(
            reverse("emergency-sos-resolve", args=[event.id]), {"status": "false_alarm"}, format="json"
        )
        assert resp.status_code == status.HTTP_200_OK
        event.refresh_from_db()
        assert event.status == "false_alarm"
        assert event.resolved_at is not None

    def test_unrelated_patient_cannot_resolve_others_event(self, patient_client):
        event = EmergencySOSEvent.objects.create(patient=PatientUserFactory())
        resp = patient_client.post(
            reverse("emergency-sos-resolve", args=[event.id]), {"status": "resolved"}, format="json"
        )
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_assigned_doctor_can_resolve(self, doctor_client, doctor_user):
        patient = PatientUserFactory()
        PatientDoctorAssignment.objects.create(patient=patient, doctor=doctor_user)
        event = EmergencySOSEvent.objects.create(patient=patient)
        resp = doctor_client.post(
            reverse("emergency-sos-resolve", args=[event.id]), {"status": "resolved"}, format="json"
        )
        assert resp.status_code == status.HTTP_200_OK
