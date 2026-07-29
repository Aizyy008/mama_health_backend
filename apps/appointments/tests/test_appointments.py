from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from apps.accounts.tests.factories import DoctorUserFactory, PatientUserFactory
from apps.appointments import services
from apps.appointments.models import Appointment, PatientDoctorAssignment
from apps.appointments.tests.factories import AppointmentFactory

pytestmark = pytest.mark.django_db


def _future():
    return timezone.now() + timedelta(days=2)


class TestBookingCreatesAssignment:
    def test_patient_books_appointment_via_api_creates_assignment(self, patient_client, patient_user):
        doctor = DoctorUserFactory()
        resp = patient_client.post(
            reverse("appointment-list"),
            {"doctor_id": doctor.id, "appointment_type": "in_person", "scheduled_at": _future().isoformat()},
            format="json",
        )
        assert resp.status_code == status.HTTP_201_CREATED
        assert resp.data["patient"]["id"] == patient_user.id
        assert PatientDoctorAssignment.objects.filter(patient=patient_user, doctor=doctor).exists()

    def test_patient_cannot_book_on_behalf_of_another_patient(self, patient_client):
        doctor = DoctorUserFactory()
        other_patient = PatientUserFactory()
        resp = patient_client.post(
            reverse("appointment-list"),
            {
                "doctor_id": doctor.id,
                "patient_id": other_patient.id,
                "appointment_type": "in_person",
                "scheduled_at": _future().isoformat(),
            },
            format="json",
        )
        assert resp.status_code == status.HTTP_201_CREATED
        # perform_create forces patient=request.user regardless of any patient_id in the payload
        assert resp.data["patient"]["id"] != other_patient.id

    def test_admin_booking_on_behalf_requires_patient_id(self, admin_client):
        doctor = DoctorUserFactory()
        resp = admin_client.post(
            reverse("appointment-list"),
            {"doctor_id": doctor.id, "appointment_type": "in_person", "scheduled_at": _future().isoformat()},
            format="json",
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_repeat_booking_with_same_doctor_does_not_duplicate_assignment(self):
        patient = PatientUserFactory()
        doctor = DoctorUserFactory()
        services.book_appointment(
            patient=patient, doctor=doctor, appointment_type="in_person", scheduled_at=_future()
        )
        services.book_appointment(
            patient=patient, doctor=doctor, appointment_type="in_person", scheduled_at=_future()
        )
        assert PatientDoctorAssignment.objects.filter(patient=patient, doctor=doctor).count() == 1

    def test_first_doctor_booked_is_marked_primary(self):
        patient = PatientUserFactory()
        doctor_a = DoctorUserFactory()
        doctor_b = DoctorUserFactory()
        services.book_appointment(
            patient=patient, doctor=doctor_a, appointment_type="in_person", scheduled_at=_future()
        )
        services.book_appointment(
            patient=patient, doctor=doctor_b, appointment_type="in_person", scheduled_at=_future()
        )
        assert PatientDoctorAssignment.objects.get(patient=patient, doctor=doctor_a).is_primary is True
        assert PatientDoctorAssignment.objects.get(patient=patient, doctor=doctor_b).is_primary is False


class TestRoleScoping:
    def test_patient_only_sees_own_appointments(self, patient_client, patient_user):
        AppointmentFactory(patient=patient_user)
        AppointmentFactory()  # someone else's
        resp = patient_client.get(reverse("appointment-list"))
        assert resp.data["count"] == 1

    def test_doctor_does_not_see_another_doctors_appointment_with_a_shared_patient(
        self, doctor_client, doctor_user
    ):
        """
        Regression test for the exact bug the bespoke permission/queryset in
        this app exists to prevent: two doctors sharing a patient must not
        see each other's appointments with that patient.
        """
        shared_patient = PatientUserFactory()
        other_doctor = DoctorUserFactory()

        mine = AppointmentFactory(patient=shared_patient, doctor=doctor_user)
        others = AppointmentFactory(patient=shared_patient, doctor=other_doctor)
        PatientDoctorAssignment.objects.create(patient=shared_patient, doctor=doctor_user)
        PatientDoctorAssignment.objects.create(patient=shared_patient, doctor=other_doctor)

        list_resp = doctor_client.get(reverse("appointment-list"))
        returned_ids = {row["id"] for row in list_resp.data["results"]}
        assert returned_ids == {mine.id}

        detail_resp = doctor_client.get(reverse("appointment-detail", args=[others.id]))
        assert detail_resp.status_code == status.HTTP_404_NOT_FOUND

    def test_admin_sees_all_appointments(self, admin_client):
        AppointmentFactory()
        AppointmentFactory()
        resp = admin_client.get(reverse("appointment-list"))
        assert resp.data["count"] == 2


class TestStatusTransitions:
    def test_valid_transition_pending_to_confirmed(self, doctor_client, doctor_user):
        appt = AppointmentFactory(doctor=doctor_user, status=Appointment.Status.PENDING)
        resp = doctor_client.post(
            reverse("appointment-update-status", args=[appt.id]), {"status": "confirmed"}, format="json"
        )
        assert resp.status_code == status.HTTP_200_OK
        appt.refresh_from_db()
        assert appt.status == Appointment.Status.CONFIRMED

    def test_invalid_transition_rejected(self, doctor_client, doctor_user):
        appt = AppointmentFactory(doctor=doctor_user, status=Appointment.Status.COMPLETED)
        resp = doctor_client.post(
            reverse("appointment-update-status", args=[appt.id]), {"status": "pending"}, format="json"
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_cancelling_records_who_cancelled(self, patient_client, patient_user):
        appt = AppointmentFactory(patient=patient_user, status=Appointment.Status.PENDING)
        resp = patient_client.post(
            reverse("appointment-update-status", args=[appt.id]),
            {"status": "cancelled", "cancellation_reason": "Schedule conflict"},
            format="json",
        )
        assert resp.status_code == status.HTTP_200_OK
        appt.refresh_from_db()
        assert appt.cancelled_by_id == patient_user.id
        assert appt.cancellation_reason == "Schedule conflict"


class TestDoctorNotes:
    def test_only_doctor_or_admin_can_set_doctor_notes(self, patient_client, doctor_client, doctor_user):
        appt = AppointmentFactory(doctor=doctor_user)
        patient_resp = patient_client.patch(
            reverse("appointment-doctor-notes", args=[appt.id]), {"doctor_notes": "hi"}, format="json"
        )
        assert patient_resp.status_code == status.HTTP_403_FORBIDDEN

        doctor_resp = doctor_client.patch(
            reverse("appointment-doctor-notes", args=[appt.id]),
            {"doctor_notes": "Patient is doing well."},
            format="json",
        )
        assert doctor_resp.status_code == status.HTTP_200_OK
        appt.refresh_from_db()
        assert appt.doctor_notes == "Patient is doing well."
