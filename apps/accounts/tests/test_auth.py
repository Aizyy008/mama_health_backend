from datetime import timedelta

import jwt as pyjwt
import pytest
from django.core import mail
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import DoctorInvite, EmailVerificationToken, PasswordResetOTP, PasswordResetToken, User
from apps.accounts.tests.factories import AdminUserFactory, DoctorUserFactory, PatientUserFactory
from apps.core.constants import Role

pytestmark = pytest.mark.django_db


class TestRegistrationAndVerification:
    def test_register_creates_unverified_patient_and_sends_email(self):
        client = APIClient()
        resp = client.post(
            reverse("auth-register"),
            {"email": "new.patient@example.com", "password": "StrongPass123!"},
            format="json",
        )
        assert resp.status_code == status.HTTP_201_CREATED
        user = User.objects.get(email="new.patient@example.com")
        assert user.role == Role.PATIENT
        assert user.is_email_verified is False
        assert len(mail.outbox) == 1

    def test_register_ignores_client_supplied_role(self):
        """A malicious payload trying to self-register as admin/doctor must still land as PATIENT."""
        client = APIClient()
        resp = client.post(
            reverse("auth-register"),
            {"email": "sneaky@example.com", "password": "StrongPass123!", "role": "admin"},
            format="json",
        )
        assert resp.status_code == status.HTTP_201_CREATED
        user = User.objects.get(email="sneaky@example.com")
        assert user.role == Role.PATIENT

    def test_register_duplicate_email_rejected(self):
        PatientUserFactory(email="dupe@example.com")
        client = APIClient()
        resp = client.post(
            reverse("auth-register"),
            {"email": "dupe@example.com", "password": "StrongPass123!"},
            format="json",
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_unverified_patient_cannot_login(self):
        user = PatientUserFactory(is_email_verified=False, password="StrongPass123!")
        client = APIClient()
        resp = client.post(
            reverse("auth-login"), {"email": user.email, "password": "StrongPass123!"}, format="json"
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_verify_email_with_valid_token_allows_login(self):
        user = PatientUserFactory(is_email_verified=False, password="StrongPass123!")
        token_record = EmailVerificationToken.objects.create(
            user=user,
            token="valid-token-123",
            expires_at=timezone.now() + timedelta(hours=1),
        )
        client = APIClient()
        resp = client.post(reverse("auth-verify-email"), {"token": token_record.token}, format="json")
        assert resp.status_code == status.HTTP_200_OK
        user.refresh_from_db()
        assert user.is_email_verified is True

        login_resp = client.post(
            reverse("auth-login"), {"email": user.email, "password": "StrongPass123!"}, format="json"
        )
        assert login_resp.status_code == status.HTTP_200_OK
        assert login_resp.data["role"] == Role.PATIENT

    def test_verify_email_with_invalid_token_rejected(self):
        client = APIClient()
        resp = client.post(reverse("auth-verify-email"), {"token": "does-not-exist"}, format="json")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_verify_email_token_is_single_use(self):
        user = PatientUserFactory(is_email_verified=False, password="StrongPass123!")
        token_record = EmailVerificationToken.objects.create(
            user=user, token="one-shot-token", expires_at=timezone.now() + timedelta(hours=1)
        )
        client = APIClient()
        first = client.post(reverse("auth-verify-email"), {"token": token_record.token}, format="json")
        second = client.post(reverse("auth-verify-email"), {"token": token_record.token}, format="json")
        assert first.status_code == status.HTTP_200_OK
        assert second.status_code == status.HTTP_400_BAD_REQUEST


class TestLoginTokenClaims:
    def test_login_embeds_role_in_jwt_claims(self):
        user = PatientUserFactory(password="StrongPass123!")
        client = APIClient()
        resp = client.post(
            reverse("auth-login"), {"email": user.email, "password": "StrongPass123!"}, format="json"
        )
        assert resp.status_code == status.HTTP_200_OK
        decoded = pyjwt.decode(resp.data["access"], options={"verify_signature": False})
        assert decoded["role"] == Role.PATIENT

    def test_deactivated_user_cannot_login(self):
        """Django's authenticate() rejects is_active=False users outright (401),
        before our custom verification-gate check ever runs."""
        user = PatientUserFactory(password="StrongPass123!", is_active=False)
        client = APIClient()
        resp = client.post(
            reverse("auth-login"), {"email": user.email, "password": "StrongPass123!"}, format="json"
        )
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED


class TestDoctorProvisioning:
    def test_only_admin_can_invite_doctor(self, patient_client, doctor_client, anon_client, admin_client):
        payload = {"email": "invitee@example.com", "specialization": "OB-GYN"}
        assert (
            patient_client.post(reverse("doctor-invite"), payload, format="json").status_code
            == status.HTTP_403_FORBIDDEN
        )
        assert (
            doctor_client.post(reverse("doctor-invite"), payload, format="json").status_code
            == status.HTTP_403_FORBIDDEN
        )
        assert (
            anon_client.post(reverse("doctor-invite"), payload, format="json").status_code
            == status.HTTP_401_UNAUTHORIZED
        )
        resp = admin_client.post(reverse("doctor-invite"), payload, format="json")
        assert resp.status_code == status.HTTP_201_CREATED
        assert DoctorInvite.objects.filter(email="invitee@example.com").exists()

    def test_accept_invite_creates_verified_doctor(self, admin_client, admin_user):
        admin_client.post(
            reverse("doctor-invite"), {"email": "doc.new@example.com"}, format="json"
        )
        invite = DoctorInvite.objects.get(email="doc.new@example.com")

        client = APIClient()
        resp = client.post(
            reverse("doctor-invite-accept"),
            {"token": invite.token, "password": "DoctorPass123!"},
            format="json",
        )
        assert resp.status_code == status.HTTP_201_CREATED
        user = User.objects.get(email="doc.new@example.com")
        assert user.role == Role.DOCTOR
        assert user.is_email_verified is True

        invite.refresh_from_db()
        assert invite.status == DoctorInvite.Status.ACCEPTED

    def test_accept_invite_token_is_single_use(self, admin_client):
        admin_client.post(reverse("doctor-invite"), {"email": "one.shot@example.com"}, format="json")
        invite = DoctorInvite.objects.get(email="one.shot@example.com")
        client = APIClient()
        payload = {"token": invite.token, "password": "DoctorPass123!"}
        first = client.post(reverse("doctor-invite-accept"), payload, format="json")
        second = client.post(reverse("doctor-invite-accept"), payload, format="json")
        assert first.status_code == status.HTTP_201_CREATED
        assert second.status_code == status.HTTP_400_BAD_REQUEST

    def test_no_public_endpoint_can_create_an_admin_account(self, admin_client):
        """Negative test: neither self-registration nor invite-acceptance can ever yield role=admin,
        even if a caller injects a "role" field into the payload."""
        client = APIClient()
        client.post(
            reverse("auth-register"),
            {"email": "wannabe.admin@example.com", "password": "StrongPass123!", "role": "admin"},
            format="json",
        )
        assert not User.objects.filter(email="wannabe.admin@example.com", role=Role.ADMIN).exists()

        admin_client.post(reverse("doctor-invite"), {"email": "wannabe.admin2@example.com"}, format="json")
        invite = DoctorInvite.objects.get(email="wannabe.admin2@example.com")
        client.post(
            reverse("doctor-invite-accept"),
            {"token": invite.token, "password": "DoctorPass123!", "role": "admin"},
            format="json",
        )
        created = User.objects.get(email="wannabe.admin2@example.com")
        assert created.role == Role.DOCTOR


class TestRoleBoundaries:
    def test_patient_list_is_admin_and_doctor_only(self, patient_client, doctor_client, admin_client):
        assert patient_client.get(reverse("patient-list")).status_code == status.HTTP_403_FORBIDDEN
        assert doctor_client.get(reverse("patient-list")).status_code == status.HTTP_200_OK
        assert admin_client.get(reverse("patient-list")).status_code == status.HTTP_200_OK

    def test_doctor_only_sees_assigned_patients_in_patient_list(self, doctor_client, doctor_user):
        from apps.appointments.models import PatientDoctorAssignment

        from apps.accounts.tests.factories import PatientUserFactory

        assigned_patient = PatientUserFactory()
        PatientUserFactory()  # not assigned to this doctor — must not appear
        PatientDoctorAssignment.objects.create(patient=assigned_patient, doctor=doctor_user)

        resp = doctor_client.get(reverse("patient-list"))
        assert resp.status_code == status.HTTP_200_OK
        returned_ids = {row["id"] for row in resp.data["results"]}
        assert returned_ids == {assigned_patient.id}

    def test_doctor_directory_readable_by_any_authenticated_role(
        self, patient_client, doctor_client, admin_client, anon_client
    ):
        DoctorUserFactory()
        assert patient_client.get(reverse("doctor-list")).status_code == status.HTTP_200_OK
        assert doctor_client.get(reverse("doctor-list")).status_code == status.HTTP_200_OK
        assert admin_client.get(reverse("doctor-list")).status_code == status.HTTP_200_OK
        assert anon_client.get(reverse("doctor-list")).status_code == status.HTTP_401_UNAUTHORIZED


class TestPatientCRUD:
    def test_admin_can_retrieve_any_patient(self, admin_client, patient_user):
        resp = admin_client.get(reverse("patient-detail", args=[patient_user.id]))
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["id"] == patient_user.id

    def test_doctor_gets_404_for_unassigned_patient(self, doctor_client, patient_user):
        resp = doctor_client.get(reverse("patient-detail", args=[patient_user.id]))
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_admin_can_deactivate_patient(self, admin_client, patient_user):
        resp = admin_client.patch(
            reverse("patient-detail", args=[patient_user.id]), {"is_active": False}, format="json"
        )
        assert resp.status_code == status.HTTP_200_OK
        patient_user.refresh_from_db()
        assert patient_user.is_active is False

    def test_doctor_cannot_update_patient(self, doctor_client, patient_user):
        resp = doctor_client.patch(
            reverse("patient-detail", args=[patient_user.id]), {"is_active": False}, format="json"
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_admin_can_assign_doctor_to_patient(self, admin_client, patient_user, doctor_user):
        from apps.appointments.models import PatientDoctorAssignment

        resp = admin_client.post(
            reverse("patient-assign-doctor", args=[patient_user.id]),
            {"doctor_id": doctor_user.id},
            format="json",
        )
        assert resp.status_code == status.HTTP_200_OK
        assert PatientDoctorAssignment.objects.filter(patient=patient_user, doctor=doctor_user).exists()

    def test_assign_doctor_is_idempotent(self, admin_client, patient_user, doctor_user):
        from apps.appointments.models import PatientDoctorAssignment

        url = reverse("patient-assign-doctor", args=[patient_user.id])
        admin_client.post(url, {"doctor_id": doctor_user.id}, format="json")
        admin_client.post(url, {"doctor_id": doctor_user.id}, format="json")
        assert PatientDoctorAssignment.objects.filter(patient=patient_user, doctor=doctor_user).count() == 1

    def test_doctor_cannot_assign_doctor(self, doctor_client, patient_user, doctor_user):
        resp = doctor_client.post(
            reverse("patient-assign-doctor", args=[patient_user.id]),
            {"doctor_id": doctor_user.id},
            format="json",
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_cannot_create_patient_directly(self, admin_client):
        resp = admin_client.post(
            reverse("patient-list"), {"email": "sneaky.direct@example.com"}, format="json"
        )
        assert resp.status_code == status.HTTP_405_METHOD_NOT_ALLOWED

    def test_admin_can_filter_patient_list_by_doctor_id(self, admin_client, doctor_user):
        from apps.appointments.models import PatientDoctorAssignment

        from apps.accounts.tests.factories import PatientUserFactory

        assigned_patient = PatientUserFactory()
        PatientUserFactory()  # not assigned — must not appear when filtered
        PatientDoctorAssignment.objects.create(patient=assigned_patient, doctor=doctor_user)

        resp = admin_client.get(reverse("patient-list"), {"doctor_id": doctor_user.id})
        assert resp.status_code == status.HTTP_200_OK
        returned_ids = {row["id"] for row in resp.data["results"]}
        assert returned_ids == {assigned_patient.id}


class TestRoleBoundariesContinued:
    def test_only_admin_can_update_doctor(self, doctor_client, admin_client):
        doc = DoctorUserFactory()
        url = reverse("doctor-detail", args=[doc.id])
        assert doctor_client.patch(url, {"is_active": False}, format="json").status_code == status.HTTP_403_FORBIDDEN
        assert admin_client.patch(url, {"is_active": False}, format="json").status_code == status.HTTP_200_OK

    def test_patient_cannot_edit_own_role_via_profile_endpoint(self, patient_client, patient_user):
        resp = patient_client.patch(
            reverse("my-patient-profile"), {"blood_group": "O+"}, format="json"
        )
        assert resp.status_code == status.HTTP_200_OK
        patient_user.refresh_from_db()
        assert patient_user.role == Role.PATIENT  # unaffected; profile endpoint can't touch role at all

    def test_doctor_cannot_access_patient_profile_endpoint(self, doctor_client):
        resp = doctor_client.get(reverse("my-patient-profile"))
        assert resp.status_code == status.HTTP_403_FORBIDDEN


class TestPasswordReset:
    def test_forgot_password_always_returns_200_even_for_unknown_email(self):
        client = APIClient()
        resp = client.post(reverse("auth-password-forgot"), {"email": "nobody@example.com"}, format="json")
        assert resp.status_code == status.HTTP_200_OK

    def test_reset_password_with_valid_token_then_login(self):
        user = PatientUserFactory(password="OldPass123!")
        record = PasswordResetToken.objects.create(
            user=user, token="reset-tok", expires_at=timezone.now() + timedelta(hours=1)
        )
        client = APIClient()
        resp = client.post(
            reverse("auth-password-reset"),
            {"token": record.token, "new_password": "NewPass123!"},
            format="json",
        )
        assert resp.status_code == status.HTTP_200_OK

        login = client.post(
            reverse("auth-login"), {"email": user.email, "password": "NewPass123!"}, format="json"
        )
        assert login.status_code == status.HTTP_200_OK

    def test_password_change_requires_correct_old_password(self, patient_client, patient_user):
        patient_user.set_password("CorrectOld123!")
        patient_user.save()
        resp = patient_client.post(
            reverse("auth-password-change"),
            {"old_password": "WrongOld123!", "new_password": "NewOne123!"},
            format="json",
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_password_change_sends_confirmation_email(self, patient_client, patient_user):
        patient_user.set_password("CorrectOld123!")
        patient_user.save()
        resp = patient_client.post(
            reverse("auth-password-change"),
            {"old_password": "CorrectOld123!", "new_password": "BrandNew123!"},
            format="json",
        )
        assert resp.status_code == status.HTTP_200_OK
        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == [patient_user.email]
        assert "changed" in mail.outbox[0].subject.lower()

    def test_password_reset_sends_confirmation_email(self):
        user = PatientUserFactory(password="OldPass123!")
        record = PasswordResetToken.objects.create(
            user=user, token="reset-tok-2", expires_at=timezone.now() + timedelta(hours=1)
        )
        client = APIClient()
        resp = client.post(
            reverse("auth-password-reset"),
            {"token": record.token, "new_password": "NewPass123!"},
            format="json",
        )
        assert resp.status_code == status.HTTP_200_OK
        assert len(mail.outbox) == 1
        assert "changed" in mail.outbox[0].subject.lower()


class TestPasswordResetOTP:
    def test_forgot_password_emails_a_6_digit_otp_not_a_link(self):
        user = PatientUserFactory(password="OldPass123!")
        client = APIClient()
        resp = client.post(reverse("auth-password-forgot"), {"email": user.email}, format="json")
        assert resp.status_code == status.HTTP_200_OK
        assert len(mail.outbox) == 1
        record = PasswordResetOTP.objects.get(user=user)
        assert len(record.otp_code) == 6
        assert record.otp_code.isdigit()
        assert record.otp_code in mail.outbox[0].body

    def test_full_otp_flow_request_then_verify_then_reset(self):
        user = PatientUserFactory(password="OldPass123!")
        client = APIClient()

        client.post(reverse("auth-password-forgot"), {"email": user.email}, format="json")
        otp = PasswordResetOTP.objects.get(user=user).otp_code

        verify_resp = client.post(
            reverse("auth-password-verify-otp"),
            {"email": user.email, "otp_code": otp},
            format="json",
        )
        assert verify_resp.status_code == status.HTTP_200_OK
        reset_token = verify_resp.data["reset_token"]

        reset_resp = client.post(
            reverse("auth-password-reset"),
            {"token": reset_token, "new_password": "BrandNewPass123!"},
            format="json",
        )
        assert reset_resp.status_code == status.HTTP_200_OK

        login = client.post(
            reverse("auth-login"), {"email": user.email, "password": "BrandNewPass123!"}, format="json"
        )
        assert login.status_code == status.HTTP_200_OK

    def test_verify_otp_rejects_wrong_code(self):
        user = PatientUserFactory()
        PasswordResetOTP.objects.create(
            user=user, otp_code="111111", expires_at=timezone.now() + timedelta(minutes=10)
        )
        client = APIClient()
        resp = client.post(
            reverse("auth-password-verify-otp"),
            {"email": user.email, "otp_code": "999999"},
            format="json",
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_verify_otp_rejects_expired_code(self):
        user = PatientUserFactory()
        PasswordResetOTP.objects.create(
            user=user, otp_code="222222", expires_at=timezone.now() - timedelta(minutes=1)
        )
        client = APIClient()
        resp = client.post(
            reverse("auth-password-verify-otp"),
            {"email": user.email, "otp_code": "222222"},
            format="json",
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_verify_otp_rejects_already_used_code(self):
        user = PatientUserFactory()
        record = PasswordResetOTP.objects.create(
            user=user,
            otp_code="333333",
            expires_at=timezone.now() + timedelta(minutes=10),
            used_at=timezone.now(),
        )
        client = APIClient()
        resp = client.post(
            reverse("auth-password-verify-otp"),
            {"email": user.email, "otp_code": record.otp_code},
            format="json",
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_requesting_a_new_otp_invalidates_the_previous_one(self):
        user = PatientUserFactory()
        client = APIClient()
        client.post(reverse("auth-password-forgot"), {"email": user.email}, format="json")
        first_otp = PasswordResetOTP.objects.get(user=user).otp_code

        client.post(reverse("auth-password-forgot"), {"email": user.email}, format="json")

        resp = client.post(
            reverse("auth-password-verify-otp"),
            {"email": user.email, "otp_code": first_otp},
            format="json",
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST


class TestProfileUpdate:
    def test_patient_can_update_own_name_and_phone(self, patient_client, patient_user):
        resp = patient_client.patch(
            reverse("auth-me"),
            {"first_name": "Updated", "phone_number": "+923001112233"},
            format="json",
        )
        assert resp.status_code == status.HTTP_200_OK
        patient_user.refresh_from_db()
        assert patient_user.first_name == "Updated"
        assert patient_user.phone_number == "+923001112233"

    def test_admin_can_update_own_profile(self, admin_client, admin_user):
        resp = admin_client.patch(reverse("auth-me"), {"first_name": "Site Admin"}, format="json")
        assert resp.status_code == status.HTTP_200_OK
        admin_user.refresh_from_db()
        assert admin_user.first_name == "Site Admin"

    def test_profile_update_cannot_touch_role_or_email(self, patient_user, patient_client):
        original_email = patient_user.email
        resp = patient_client.patch(
            reverse("auth-me"), {"role": "admin", "email": "hijacked@example.com"}, format="json"
        )
        assert resp.status_code == status.HTTP_200_OK
        patient_user.refresh_from_db()
        assert patient_user.role == Role.PATIENT
        assert patient_user.email == original_email
