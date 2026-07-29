import secrets
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from apps.accounts.models import (
    DoctorInvite,
    DoctorProfile,
    EmailVerificationToken,
    PasswordResetToken,
    PatientProfile,
    User,
)
from apps.core.constants import Role


def generate_token() -> str:
    return secrets.token_urlsafe(32)


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
    PatientProfile.objects.create(user=user)
    send_email_verification(user)
    return user


def send_email_verification(user: User) -> None:
    token = generate_token()
    expires_at = timezone.now() + timedelta(hours=settings.EMAIL_VERIFICATION_TOKEN_EXPIRY_HOURS)
    EmailVerificationToken.objects.create(user=user, token=token, expires_at=expires_at)
    verify_url = f"{settings.FRONTEND_URL}/verify-email?token={token}"
    send_mail(
        subject="Verify your Mama Health account",
        message=(
            f"Welcome to Mama Health! Verify your email to activate your account:\n\n{verify_url}\n\n"
            f"This link expires in {settings.EMAIL_VERIFICATION_TOKEN_EXPIRY_HOURS} hours."
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
    )


def verify_email(token: str) -> User:
    try:
        record = EmailVerificationToken.objects.select_related("user").get(token=token, used_at__isnull=True)
    except EmailVerificationToken.DoesNotExist as exc:
        raise ValueError("Invalid or already-used verification token.") from exc
    if record.expires_at < timezone.now():
        raise ValueError("Verification token has expired. Please request a new one.")

    record.used_at = timezone.now()
    record.save(update_fields=["used_at"])
    user = record.user
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
    try:
        user = User.objects.get(email__iexact=email)
    except User.DoesNotExist:
        return  # don't leak account existence

    token = generate_token()
    expires_at = timezone.now() + timedelta(hours=settings.PASSWORD_RESET_TOKEN_EXPIRY_HOURS)
    PasswordResetToken.objects.create(user=user, token=token, expires_at=expires_at)
    reset_url = f"{settings.FRONTEND_URL}/reset-password?token={token}"
    send_mail(
        subject="Reset your Mama Health password",
        message=(
            f"Reset your password:\n\n{reset_url}\n\n"
            f"This link expires in {settings.PASSWORD_RESET_TOKEN_EXPIRY_HOURS} hours. "
            "If you didn't request this, you can safely ignore this email."
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
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
    return user


def invite_doctor(*, email: str, invited_by: User, specialization: str = "") -> DoctorInvite:
    token = generate_token()
    expires_at = timezone.now() + timedelta(days=settings.DOCTOR_INVITE_EXPIRY_DAYS)
    invite = DoctorInvite.objects.create(
        email=email,
        invited_by=invited_by,
        specialization=specialization,
        token=token,
        expires_at=expires_at,
    )
    accept_url = f"{settings.FRONTEND_URL}/doctor-invite?token={token}"
    send_mail(
        subject="You've been invited to Mama Health",
        message=(
            "You've been invited to join Mama Health as a doctor. "
            f"Set your password to activate your account:\n\n{accept_url}\n\n"
            f"This link expires in {settings.DOCTOR_INVITE_EXPIRY_DAYS} days."
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[email],
    )
    return invite


def accept_doctor_invite(
    *, token: str, password: str, first_name: str = "", last_name: str = "", phone_number: str = ""
) -> User:
    try:
        invite = DoctorInvite.objects.get(token=token, status=DoctorInvite.Status.PENDING)
    except DoctorInvite.DoesNotExist as exc:
        raise ValueError("Invalid or already-used invite token.") from exc

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
