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
    # Manual-payment subscription (client explicitly rejected a paid payment
    # gateway integration for now — see apps/accounts/subscriptions.py).
    # Set once at registration; trial_ends_at never changes afterward.
    # is_paid is a one-way admin-toggled flag (apps/accounts/views.py::
    # PatientViewSet.mark_paid) — no recurring/expiry logic since there's no
    # automated payment collection to expire it against yet.
    trial_ends_at = models.DateTimeField(null=True, blank=True)
    is_paid = models.BooleanField(default=False)
    paid_at = models.DateTimeField(null=True, blank=True)
    paid_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="marked_patient_payments"
    )
    payment_reference = models.CharField(
        max_length=255, blank=True, help_text="Admin's free-text note, e.g. a JazzCash transaction ID."
    )

    def __str__(self):
        return f"PatientProfile<{self.user.email}>"


class PlatformPaymentMethod(models.Model):
    """
    Singleton (always pk=1, enforced in save()) admin-configured payment
    details shown to patients so they know where to manually send money —
    JazzCash/EasyPaisa/bank transfer, not an integrated payment gateway.
    All fields optional/blank: admin fills in whichever methods are
    actually available, the API just omits the empty ones from what it
    shows patients.
    """

    jazzcash_number = models.CharField(max_length=20, blank=True)
    jazzcash_account_title = models.CharField(max_length=150, blank=True)
    easypaisa_number = models.CharField(max_length=20, blank=True)
    easypaisa_account_title = models.CharField(max_length=150, blank=True)
    bank_name = models.CharField(max_length=150, blank=True)
    bank_account_title = models.CharField(max_length=150, blank=True)
    bank_account_number = models.CharField(max_length=50, blank=True)
    bank_iban = models.CharField(max_length=50, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        pass  # singleton — never actually deletable

    @classmethod
    def load(cls) -> "PlatformPaymentMethod":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return "Platform payment methods"


class PakistaniCity(models.TextChoices):
    """
    Fixed dropdown (not free text) so city filtering doesn't have to deal
    with "Lahore" vs "lahore" vs "Lahor" — client explicitly asked for a
    free (no paid maps API) city/area dropdown search, added to a live
    "OTHER" fallback for any city not in the initial list.
    """

    KARACHI = "karachi", "Karachi"
    LAHORE = "lahore", "Lahore"
    ISLAMABAD = "islamabad", "Islamabad"
    RAWALPINDI = "rawalpindi", "Rawalpindi"
    FAISALABAD = "faisalabad", "Faisalabad"
    MULTAN = "multan", "Multan"
    PESHAWAR = "peshawar", "Peshawar"
    QUETTA = "quetta", "Quetta"
    HYDERABAD = "hyderabad", "Hyderabad"
    SIALKOT = "sialkot", "Sialkot"
    GUJRANWALA = "gujranwala", "Gujranwala"
    SARGODHA = "sargodha", "Sargodha"
    BAHAWALPUR = "bahawalpur", "Bahawalpur"
    SUKKUR = "sukkur", "Sukkur"
    OTHER = "other", "Other"


class DoctorProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="doctor_profile")
    specialization = models.CharField(max_length=150, blank=True)
    license_number = models.CharField(max_length=100, blank=True)
    years_of_experience = models.PositiveIntegerField(null=True, blank=True)
    bio = models.TextField(blank=True)
    is_accepting_patients = models.BooleanField(default=True)
    # Free city/area search (client explicitly rejected a paid maps API):
    # doctor picks their city from a fixed dropdown + free-text area, and
    # patients filter by either. latitude/longitude are optional — only
    # needed for the "near me" radius search, computed with a plain
    # Haversine formula (apps/accounts/geo.py), no external API/key.
    city = models.CharField(max_length=20, choices=PakistaniCity.choices, blank=True)
    area = models.CharField(max_length=100, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

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
