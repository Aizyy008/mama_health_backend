from django.contrib.auth.models import AbstractUser
from django.db import models

from apps.accounts.managers import UserManager
from apps.core.constants import Role
from apps.core.models import TimeStampedModel


class User(AbstractUser):
    username = None
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=20, choices=Role.choices)
    phone_number = models.CharField(max_length=20, blank=True)
    is_email_verified = models.BooleanField(default=False)
    fcm_device_token = models.CharField(max_length=255, blank=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        ordering = ["-date_joined"]

    def __str__(self):
        return self.email


class PatientProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="patient_profile")
    date_of_birth = models.DateField(null=True, blank=True)
    lmp_date = models.DateField(null=True, blank=True, help_text="Last Menstrual Period date")
    edd_date = models.DateField(null=True, blank=True, help_text="Estimated Due Date; auto-derived from lmp_date if not set")
    blood_group = models.CharField(max_length=5, blank=True)
    emergency_contact_name = models.CharField(max_length=100, blank=True)
    emergency_contact_phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    profile_complete = models.BooleanField(default=False)

    def __str__(self):
        return f"PatientProfile<{self.user.email}>"


class DoctorProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="doctor_profile")
    specialization = models.CharField(max_length=150, blank=True)
    license_number = models.CharField(max_length=100, blank=True)
    years_of_experience = models.PositiveIntegerField(null=True, blank=True)
    bio = models.TextField(blank=True)
    is_accepting_patients = models.BooleanField(default=True)

    def __str__(self):
        return f"DoctorProfile<{self.user.email}>"


class DoctorInvite(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        EXPIRED = "expired", "Expired"

    email = models.EmailField()
    invited_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="doctor_invites_sent"
    )
    specialization = models.CharField(max_length=150, blank=True)
    # 6-digit OTP, not a URL token — invite acceptance happens in the mobile
    # app (email a link, not a code, doesn't reliably work: tapping an
    # https:// link opens a browser, not the app, without real deep-link
    # setup). Not unique=True: a 6-digit space collides eventually at scale,
    # disambiguated instead by (email, otp_code, status=PENDING) at lookup.
    otp_code = models.CharField(max_length=6)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    expires_at = models.DateTimeField()

    def __str__(self):
        return f"DoctorInvite<{self.email}, {self.status}>"


class EmailVerificationToken(TimeStampedModel):
    """Despite the model name (kept for migration/history continuity), this
    stores a 6-digit OTP, not a URL token — same reasoning as DoctorInvite."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="verification_tokens")
    otp_code = models.CharField(max_length=6)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)


class PasswordResetToken(TimeStampedModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="password_reset_tokens")
    token = models.CharField(max_length=128, unique=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)


class PasswordResetOTP(TimeStampedModel):
    """
    6-digit code emailed for the forgot-password flow's first step. Verifying
    one (see accounts.services.verify_password_reset_otp) issues a
    PasswordResetToken for the actual /password/reset/ step, so the OTP
    itself is single-purpose (proves email ownership) and short-lived.
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="password_reset_otps")
    otp_code = models.CharField(max_length=6)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
