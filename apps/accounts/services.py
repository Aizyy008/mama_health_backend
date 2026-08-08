import secrets
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from apps.accounts.emails import send_transactional_email
from apps.accounts.models import (
    DoctorInvite,
    DoctorProfile,
    EmailVerificationToken,
    PasswordResetOTP,
    PasswordResetToken,
    PatientProfile,
    User,
)
from apps.core.constants import Role


def generate_token() -> str:
    return secrets.token_urlsafe(32)


def generate_otp_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def register_patient(*, email, password, first_name="", last_name="", phone_number=""):
    user = User.objects.create_user(
        email=email,
        password=password,
        role=Role.PATIENT,
        first_name=first_name,
        last_name=last_name,
        phone_number=phone_number,
        is_email_verified=False,
    )
    trial_ends_at = timezone.now() + timedelta(days=settings.PATIENT_TRIAL_DAYS)
    PatientProfile.objects.create(user=user, trial_ends_at=trial_ends_at)
    send_email_verification(user)
    return user


def send_email_verification(user: User) -> None:
    """
    Emails a 6-digit OTP, not a link — patients are mobile-only, and an
    https:// link in an email just opens a browser, not the app, without
    real deep-link (Universal Links/App Links) setup. Any previously
    unused code for this user is invalidated first, same reasoning as
    password-reset OTPs: only the most recently requested code is valid.
    """
    EmailVerificationToken.objects.filter(user=user, used_at__isnull=True).update(used_at=timezone.now())

    otp_code = generate_otp_code()
    expires_at = timezone.now() + timedelta(hours=settings.EMAIL_VERIFICATION_TOKEN_EXPIRY_HOURS)
    EmailVerificationToken.objects.create(user=user, otp_code=otp_code, expires_at=expires_at)
    send_transactional_email(
        subject="Verify your Mama Health account",
        template_name="emails/verify_email.html",
        context={"otp_code": otp_code, "expiry_hours": settings.EMAIL_VERIFICATION_TOKEN_EXPIRY_HOURS},
        to=user.email,
        plain_message=(
            f"Welcome to Mama Health! Your verification code is: {otp_code}\n\n"
            f"This code expires in {settings.EMAIL_VERIFICATION_TOKEN_EXPIRY_HOURS} hours."
        ),
    )


def verify_email(*, email: str, otp_code: str) -> User:
    try:
        user = User.objects.get(email__iexact=email)
    except User.DoesNotExist as exc:
        raise ValueError("Invalid or expired code. Please request a new one.") from exc

    try:
        record = EmailVerificationToken.objects.filter(
            user=user, otp_code=otp_code, used_at__isnull=True
        ).latest("created_at")
    except EmailVerificationToken.DoesNotExist as exc:
        raise ValueError("Invalid or expired code. Please request a new one.") from exc
    if record.expires_at < timezone.now():
        raise ValueError("This code has expired. Please request a new one.")

    record.used_at = timezone.now()
    record.save(update_fields=["used_at"])
    user.is_email_verified = True
    user.save(update_fields=["is_email_verified"])
    return user


def resend_verification(email: str) -> None:
    try:
        user = User.objects.get(email__iexact=email, is_email_verified=False)
    except User.DoesNotExist:
        return  # don't leak account existence/verification state
    send_email_verification(user)


def request_password_reset(email: str) -> None:
    """
    Step 1 of the forgot-password flow: emails a 6-digit OTP (not a link).
    Always silent on a nonexistent email (doesn't leak account existence).
    Any previously-issued, still-unused OTPs for this user are invalidated
    so only the most recently requested code is valid — prevents an old,
    leaked-but-unused code from staying usable indefinitely.
    """
    try:
        user = User.objects.get(email__iexact=email)
    except User.DoesNotExist:
        return  # don't leak account existence

    PasswordResetOTP.objects.filter(user=user, used_at__isnull=True).update(used_at=timezone.now())

    otp_code = generate_otp_code()
    expires_at = timezone.now() + timedelta(minutes=settings.PASSWORD_RESET_OTP_EXPIRY_MINUTES)
    PasswordResetOTP.objects.create(user=user, otp_code=otp_code, expires_at=expires_at)
    send_transactional_email(
        subject="Your Mama Health password reset code",
        template_name="emails/password_reset_otp.html",
        context={"otp_code": otp_code, "expiry_minutes": settings.PASSWORD_RESET_OTP_EXPIRY_MINUTES},
        to=user.email,
        plain_message=(
            f"Your password reset code is: {otp_code}\n\n"
            f"This code expires in {settings.PASSWORD_RESET_OTP_EXPIRY_MINUTES} minutes. "
            "If you didn't request this, you can safely ignore this email."
        ),
    )


def verify_password_reset_otp(*, email: str, otp_code: str) -> str:
    """
    Step 2: checks the code and, on success, issues a PasswordResetToken
    (the same mechanism /password/reset/ already consumed under the old
    link-based flow) so the frontend doesn't need to resubmit the OTP again
    at the final step. Raises ValueError with a message safe to show the
    user (this endpoint is inherently email-scoped, so it doesn't need to
    stay silent about existence the way the request step does).
    """
    try:
        user = User.objects.get(email__iexact=email)
    except User.DoesNotExist as exc:
        raise ValueError("Invalid or expired code. Please request a new one.") from exc

    try:
        record = PasswordResetOTP.objects.filter(user=user, otp_code=otp_code, used_at__isnull=True).latest(
            "created_at"
        )
    except PasswordResetOTP.DoesNotExist as exc:
        raise ValueError("Invalid or expired code. Please request a new one.") from exc

    if record.expires_at < timezone.now():
        raise ValueError("This code has expired. Please request a new one.")

    record.used_at = timezone.now()
    record.save(update_fields=["used_at"])

    token = generate_token()
    expires_at = timezone.now() + timedelta(hours=settings.PASSWORD_RESET_TOKEN_EXPIRY_HOURS)
    PasswordResetToken.objects.create(user=user, token=token, expires_at=expires_at)
    return token


def send_password_changed_email(user: User) -> None:
    """
    Security notice sent after any successful password change — via
    /password/reset/ (OTP flow) or /password/change/ (authenticated,
    knows current password). Not the OTP/reset-link emails themselves;
    this fires only once the password has actually been updated, so the
    user notices if they didn't make the change.
    """
    send_transactional_email(
        subject="Your Mama Health password was changed",
        template_name="emails/password_changed.html",
        context={},
        to=user.email,
        plain_message=(
            "This is a confirmation that your Mama Health account password was just changed.\n\n"
            "If you made this change, no action is needed. If you didn't, reset your password "
            "immediately via the app's forgot-password flow and contact support."
        ),
    )


def reset_password(*, token: str, new_password: str) -> User:
    try:
        record = PasswordResetToken.objects.select_related("user").get(token=token, used_at__isnull=True)
    except PasswordResetToken.DoesNotExist as exc:
        raise ValueError("Invalid or already-used reset token.") from exc
    if record.expires_at < timezone.now():
        raise ValueError("Reset token has expired. Please request a new one.")

    record.used_at = timezone.now()
    record.save(update_fields=["used_at"])
    user = record.user
    user.set_password(new_password)
    user.save(update_fields=["password"])
    send_password_changed_email(user)
    return user


def invite_doctor(*, email: str, invited_by: User, specialization: str = "") -> DoctorInvite:
    otp_code = generate_otp_code()
    expires_at = timezone.now() + timedelta(days=settings.DOCTOR_INVITE_EXPIRY_DAYS)
    invite = DoctorInvite.objects.create(
        email=email,
        invited_by=invited_by,
        specialization=specialization,
        otp_code=otp_code,
        expires_at=expires_at,
    )
    send_transactional_email(
        subject="You've been invited to Mama Health",
        template_name="emails/doctor_invite.html",
        context={
            "otp_code": otp_code,
            "specialization": specialization,
            "expiry_days": settings.DOCTOR_INVITE_EXPIRY_DAYS,
        },
        to=email,
        plain_message=(
            "You've been invited to join Mama Health as a doctor. "
            f"Open the app and enter this code to set up your account: {otp_code}\n\n"
            f"This code expires in {settings.DOCTOR_INVITE_EXPIRY_DAYS} days."
        ),
    )
    return invite


def accept_doctor_invite(
    *, email: str, otp_code: str, password: str, first_name: str = "", last_name: str = "", phone_number: str = ""
) -> User:
    try:
        invite = DoctorInvite.objects.filter(
            email__iexact=email, otp_code=otp_code, status=DoctorInvite.Status.PENDING
        ).latest("created_at")
    except DoctorInvite.DoesNotExist as exc:
        raise ValueError("Invalid or already-used invite code.") from exc

    if invite.expires_at < timezone.now():
        invite.status = DoctorInvite.Status.EXPIRED
        invite.save(update_fields=["status"])
        raise ValueError("This invite has expired. Ask an admin to send a new one.")

    user = User.objects.create_user(
        email=invite.email,
        password=password,
        role=Role.DOCTOR,
        first_name=first_name,
        last_name=last_name,
        phone_number=phone_number,
        is_email_verified=True,  # accepting the invite email itself proves ownership
    )
    DoctorProfile.objects.create(user=user, specialization=invite.specialization)

    invite.status = DoctorInvite.Status.ACCEPTED
    invite.save(update_fields=["status"])
    return user


def mark_patient_paid(*, patient_profile, admin: User, payment_reference: str = "") -> None:
    """Admin manually confirming a JazzCash/EasyPaisa/bank transfer happened outside the app."""
    patient_profile.is_paid = True
    patient_profile.paid_at = timezone.now()
    patient_profile.paid_by = admin
    patient_profile.payment_reference = payment_reference
    patient_profile.save(update_fields=["is_paid", "paid_at", "paid_by", "payment_reference"])


_DUMMY_DOCTORS = [
    {
        "email": "dummy.doctor1@mamahealth-test.app",
        "first_name": "Ayesha",
        "last_name": "Malik",
        "phone_number": "+923001234567",
        "specialization": "OB-GYN",
        "license_number": "PMC-00001",
        "years_of_experience": 8,
        "bio": "Dummy test doctor — safe to delete once real doctors are onboarded.",
        "city": "lahore",
        "area": "DHA Phase 5",
        "latitude": 31.4708,
        "longitude": 74.4104,
    },
    {
        "email": "dummy.doctor2@mamahealth-test.app",
        "first_name": "Sana",
        "last_name": "Khan",
        "phone_number": "+923007654321",
        "specialization": "Gynecologist",
        "license_number": "PMC-00002",
        "years_of_experience": 5,
        "bio": "Dummy test doctor — safe to delete once real doctors are onboarded.",
        "city": "karachi",
        "area": "Clifton",
        "latitude": 24.8138,
        "longitude": 67.0300,
    },
]


DUMMY_ACCOUNT_PASSWORD = "TestPass123!"


def seed_dummy_doctors() -> list[User]:
    """
    Frontend-integration convenience, not a general-purpose feature: creates
    a couple of clearly-marked (@mamahealth-test.app) dummy doctors directly
    (bypassing the normal invite flow, which needs a real inbox to receive
    the OTP) so Saad's Flutter app has something to list/search against —
    and log in as, via DUMMY_ACCOUNT_PASSWORD — before real doctors are
    onboarded. Idempotent — safe to call more than once (also re-applies
    the known password, in case it was ever changed). Delete these via
    Django admin before handing admin access to the client (identifiable
    by the @mamahealth-test.app email domain).
    """
    users = []
    for data in _DUMMY_DOCTORS:
        profile_fields = {
            key: data[key]
            for key in ("specialization", "license_number", "years_of_experience", "bio", "city", "area", "latitude", "longitude")
        }
        user_fields = {key: data[key] for key in ("first_name", "last_name", "phone_number")}
        user, _ = User.objects.get_or_create(
            email=data["email"],
            defaults={**user_fields, "role": Role.DOCTOR, "is_email_verified": True, "is_active": True},
        )
        user.set_password(DUMMY_ACCOUNT_PASSWORD)
        user.save()
        DoctorProfile.objects.update_or_create(user=user, defaults=profile_fields)
        users.append(user)
    return users


def seed_dummy_patient_appointment_and_sos() -> dict:
    """
    Follow-up to seed_dummy_doctors: Saad also needed one appointment and
    one SOS event to test those list screens, and there was no patient in
    production to attach them to (patients only ever exist via real
    self-registration). Creates one clearly-marked
    (@mamahealth-test.app) dummy patient — real login via
    DUMMY_ACCOUNT_PASSWORD, same as the dummy doctors — with one
    appointment against the first dummy doctor and one active Emergency
    SOS event. Idempotent. Delete via Django admin (identifiable by the
    @mamahealth-test.app email domain) before handing admin access to
    the client, same as the dummy doctors.
    """
    from datetime import date

    from apps.appointments import services as appointment_services
    from apps.appointments.models import Appointment
    from apps.emergency.models import EmergencySOSEvent

    doctors = seed_dummy_doctors()
    doctor = doctors[0]

    patient, _ = User.objects.get_or_create(
        email="dummy.patient1@mamahealth-test.app",
        defaults={
            "first_name": "Sara",
            "last_name": "Ahmed",
            "phone_number": "+923001112222",
            "role": Role.PATIENT,
            "is_email_verified": True,
            "is_active": True,
        },
    )
    patient.set_password(DUMMY_ACCOUNT_PASSWORD)
    patient.save()
    PatientProfile.objects.update_or_create(
        user=patient,
        defaults={
            "date_of_birth": date(1995, 6, 20),
            "lmp_date": date.today() - timedelta(weeks=12),
            "blood_group": "O+",
            "profile_complete": True,
            "trial_ends_at": timezone.now() + timedelta(days=7),
        },
    )

    if not Appointment.objects.filter(patient=patient, doctor=doctor).exists():
        appointment_services.book_appointment(
            patient=patient,
            doctor=doctor,
            appointment_type="in_person",
            scheduled_at=timezone.now() + timedelta(days=2),
            reason="Routine checkup (dummy seed data for frontend testing)",
        )

    EmergencySOSEvent.objects.get_or_create(
        patient=patient,
        notes="Dummy SOS event for frontend testing — safe to delete.",
        defaults={
            "status": EmergencySOSEvent.Status.ACTIVE,
            "latitude": 31.4708,
            "longitude": 74.4104,
        },
    )
    return {"patient": patient, "doctor": doctor}


def reset_admin_password(*, email: str, new_password: str) -> None:
    """
    One-off maintenance action (client-accidentally-changed-the-password
    recovery), not a general-purpose feature — see
    apps/core/views.py::reset_admin_password_emergency for why this takes
    the password as an argument rather than a hardcoded value: hardcoding
    a real production credential into source code would put it in git
    history on a public repo.
    """
    user = User.objects.get(email__iexact=email, role=Role.ADMIN)
    user.set_password(new_password)
    user.save(update_fields=["password"])
