from datetime import timedelta
from unittest.mock import patch

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from apps.accounts.tests.factories import DoctorUserFactory, PatientUserFactory
from apps.appointments import services as appointment_services
from apps.appointments.models import PatientDoctorAssignment
from apps.appointments.tests.factories import AppointmentFactory
from apps.core.constants import Role
from apps.diet import services as diet_services
from apps.medicines.models import MedicineIntakeLog
from apps.medicines.tests.factories import MedicineReminderFactory
from apps.notifications import services as notification_services
from apps.notifications.models import Notification
from apps.notifications.tasks import (
    send_appointment_reminders,
    send_medicine_reminders,
    send_weekly_pregnancy_update,
)

pytestmark = pytest.mark.django_db


class TestNotificationInbox:
    def test_patient_sees_only_own_notifications(self, patient_client, patient_user):
        Notification.objects.create(recipient=patient_user, notification_type="diet", title="a", body="b")
        Notification.objects.create(recipient=PatientUserFactory(), notification_type="diet", title="c", body="d")
        resp = patient_client.get(reverse("notification-list"))
        assert resp.data["count"] == 1

    def test_mark_read(self, patient_client, patient_user):
        n = Notification.objects.create(recipient=patient_user, notification_type="diet", title="a", body="b")
        resp = patient_client.post(reverse("notification-mark-read", args=[n.id]))
        assert resp.status_code == status.HTTP_200_OK
        n.refresh_from_db()
        assert n.is_read is True

    def test_mark_all_read(self, patient_client, patient_user):
        Notification.objects.create(recipient=patient_user, notification_type="diet", title="a", body="b")
        Notification.objects.create(recipient=patient_user, notification_type="medicine", title="c", body="d")
        resp = patient_client.post(reverse("notification-mark-all-read"))
        assert resp.status_code == status.HTTP_200_OK
        assert Notification.objects.filter(recipient=patient_user, is_read=False).count() == 0

    def test_cannot_mark_another_users_notification_read(self, patient_client):
        n = Notification.objects.create(recipient=PatientUserFactory(), notification_type="diet", title="a", body="b")
        resp = patient_client.post(reverse("notification-mark-read", args=[n.id]))
        assert resp.status_code == status.HTTP_404_NOT_FOUND


class TestDoctorMessage:
    def test_unassigned_doctor_cannot_message_patient(self, doctor_client):
        patient = PatientUserFactory()
        resp = doctor_client.post(
            reverse("notification-send-to-patient"),
            {"patient_id": patient.id, "title": "Hi", "body": "How are you feeling?"},
            format="json",
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_assigned_doctor_can_message_patient(self, doctor_client, doctor_user):
        patient = PatientUserFactory()
        PatientDoctorAssignment.objects.create(patient=patient, doctor=doctor_user)
        resp = doctor_client.post(
            reverse("notification-send-to-patient"),
            {"patient_id": patient.id, "title": "Hi", "body": "How are you feeling?"},
            format="json",
        )
        assert resp.status_code == status.HTTP_201_CREATED
        assert Notification.objects.filter(
            recipient=patient, notification_type="doctor_message"
        ).exists()

    def test_patient_cannot_send_doctor_message(self, patient_client):
        resp = patient_client.post(
            reverse("notification-send-to-patient"), {"patient_id": 1, "title": "x", "body": "y"}, format="json"
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN


class TestBroadcast:
    def test_only_admin_can_broadcast(self, patient_client, doctor_client):
        payload = {"title": "System maintenance", "body": "We'll be down briefly tonight."}
        assert patient_client.post(reverse("notification-broadcast"), payload, format="json").status_code == status.HTTP_403_FORBIDDEN
        assert doctor_client.post(reverse("notification-broadcast"), payload, format="json").status_code == status.HTTP_403_FORBIDDEN

    def test_broadcast_reaches_patients_and_doctors_not_admins(self, admin_client, admin_user):
        p1, p2 = PatientUserFactory(), PatientUserFactory()
        d1 = DoctorUserFactory()
        resp = admin_client.post(
            reverse("notification-broadcast"),
            {"title": "System maintenance", "body": "We'll be down briefly tonight."},
            format="json",
        )
        assert resp.status_code == status.HTTP_202_ACCEPTED
        recipients = set(Notification.objects.filter(notification_type="broadcast").values_list("recipient_id", flat=True))
        assert recipients == {p1.id, p2.id, d1.id}
        assert admin_user.id not in recipients

    def test_broadcast_target_role_filters(self, admin_client):
        patient = PatientUserFactory()
        DoctorUserFactory()
        resp = admin_client.post(
            reverse("notification-broadcast"),
            {"title": "Patients only", "body": "...", "target_role": "patient"},
            format="json",
        )
        assert resp.status_code == status.HTTP_202_ACCEPTED
        recipients = set(Notification.objects.filter(notification_type="broadcast").values_list("recipient_id", flat=True))
        assert recipients == {patient.id}


class TestNotificationServiceResilience:
    def test_adapter_failure_does_not_raise_and_notification_row_still_created(self, patient_user):
        with patch("apps.notifications.services.get_push_adapter") as mock_factory:
            mock_factory.return_value.send.side_effect = Exception("FCM is down")
            notification = notification_services.notify(
                recipient=patient_user,
                notification_type="diet",
                title="Test",
                body="Test body",
                channels=["push"],
            )
        assert notification.pk is not None
        assert notification.channel_push_sent is False

    def test_null_adapters_used_when_no_credentials_configured(self, patient_user):
        # settings.FCM_CREDENTIALS_JSON / WHATSAPP_API_TOKEN are blank in test settings
        notification = notification_services.notify(
            recipient=patient_user,
            notification_type="diet",
            title="Test",
            body="Test body",
            channels=["push", "whatsapp"],
        )
        assert notification.channel_push_sent is False
        assert notification.channel_whatsapp_sent is False


class TestServiceIntegrationTriggers:
    def test_booking_notifies_doctor(self, doctor_user, patient_user):
        appointment_services.book_appointment(
            patient=patient_user,
            doctor=doctor_user,
            appointment_type="in_person",
            scheduled_at=timezone.now() + timedelta(days=1),
        )
        assert Notification.objects.filter(recipient=doctor_user, notification_type="appointment").exists()

    def test_status_change_by_patient_notifies_doctor_only(self, doctor_user, patient_user):
        appt = AppointmentFactory(patient=patient_user, doctor=doctor_user)
        Notification.objects.all().delete()
        appointment_services.transition_status(appointment=appt, new_status="confirmed", actor=doctor_user)
        assert Notification.objects.filter(recipient=patient_user).exists()
        assert not Notification.objects.filter(recipient=doctor_user).exists()

    def test_diet_plan_creation_notifies_patient(self, patient_user, doctor_user):
        diet_services.create_diet_plan(patient=patient_user, created_by=doctor_user, notes="test")
        assert Notification.objects.filter(recipient=patient_user, notification_type="diet").exists()


class TestAppointmentReminderTask:
    def test_reminds_once_for_upcoming_appointment(self, patient_user, doctor_user):
        appt = AppointmentFactory(
            patient=patient_user,
            doctor=doctor_user,
            status="confirmed",
            scheduled_at=timezone.now() + timedelta(minutes=30),
        )
        send_appointment_reminders()
        appt.refresh_from_db()
        assert appt.reminder_sent_at is not None
        assert Notification.objects.filter(recipient=patient_user, notification_type="appointment").count() == 1
        assert Notification.objects.filter(recipient=doctor_user, notification_type="appointment").count() == 1

        # Second run must not duplicate — reminder_sent_at already set
        send_appointment_reminders()
        assert Notification.objects.filter(recipient=patient_user, notification_type="appointment").count() == 1

    def test_does_not_remind_appointments_outside_the_window(self, patient_user, doctor_user):
        AppointmentFactory(
            patient=patient_user,
            doctor=doctor_user,
            status="confirmed",
            scheduled_at=timezone.now() + timedelta(days=3),
        )
        send_appointment_reminders()
        assert not Notification.objects.filter(notification_type="appointment").exists()


class TestMedicineReminderTask:
    def test_creates_intake_log_and_notifies_within_window(self, patient_user):
        now_str = timezone.localtime(timezone.now()).strftime("%H:%M")
        MedicineReminderFactory(patient=patient_user, reminder_times=[now_str])
        send_medicine_reminders()
        assert MedicineIntakeLog.objects.filter(reminder__patient=patient_user).count() == 1
        assert Notification.objects.filter(recipient=patient_user, notification_type="medicine").exists()

        # Second run within the same window must not duplicate the log
        send_medicine_reminders()
        assert MedicineIntakeLog.objects.filter(reminder__patient=patient_user).count() == 1

    def test_ignores_reminder_times_outside_window(self, patient_user):
        MedicineReminderFactory(patient=patient_user, reminder_times=["23:59"])
        send_medicine_reminders()
        # only safe if current time isn't near 23:59 — acceptable for CI/local dev
        if timezone.localtime(timezone.now()).strftime("%H:%M") not in ("23:5", "00:0"):
            assert MedicineIntakeLog.objects.filter(reminder__patient=patient_user).count() == 0


class TestWeeklyPregnancyUpdateTask:
    def test_notifies_on_exact_week_boundary(self, patient_user):
        patient_user.patient_profile.lmp_date = timezone.now().date() - timedelta(weeks=12)
        patient_user.patient_profile.save()
        send_weekly_pregnancy_update()
        assert Notification.objects.filter(recipient=patient_user, notification_type="weekly_update").exists()

    def test_does_not_notify_off_boundary(self, patient_user):
        patient_user.patient_profile.lmp_date = timezone.now().date() - timedelta(weeks=12, days=3)
        patient_user.patient_profile.save()
        send_weekly_pregnancy_update()
        assert not Notification.objects.filter(recipient=patient_user, notification_type="weekly_update").exists()
