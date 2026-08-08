from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from apps.accounts import services
from apps.accounts.models import DoctorInvite, DoctorProfile, PatientProfile, PlatformPaymentMethod, User
from apps.core.constants import Role


class BriefUserSerializer(serializers.ModelSerializer):
    """Minimal user representation for nesting inside other apps' serializers
    (e.g. an Appointment's patient/doctor, a DietPlan's created_by)."""

    class Meta:
        model = User
        fields = ["id", "email", "first_name", "last_name"]


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, validators=[validate_password])
    first_name = serializers.CharField(required=False, allow_blank=True, default="")
    last_name = serializers.CharField(required=False, allow_blank=True, default="")
    phone_number = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError(
                "An account with this email already exists. Please log in or use a different email."
            )
        return value

    def create(self, validated_data):
        return services.register_patient(**validated_data)


class VerifyEmailSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp_code = serializers.CharField(min_length=6, max_length=6)


class ResendVerificationSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordForgotSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordVerifyOTPSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp_code = serializers.CharField(min_length=6, max_length=6)


class PasswordVerifyOTPResponseSerializer(serializers.Serializer):
    """Schema-only, for Swagger — the view builds this response dict itself."""

    detail = serializers.CharField()
    reset_token = serializers.CharField()


class PasswordResetSerializer(serializers.Serializer):
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True, validators=[validate_password])


class PasswordChangeSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, validators=[validate_password])

    def validate_old_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("The old password you entered is incorrect. Please try again.")
        return value


class MamaHealthTokenObtainPairSerializer(TokenObtainPairSerializer):
    default_error_messages = {
        "no_active_account": "Please enter a valid email and password.",
    }

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["role"] = user.role
        token["is_email_verified"] = user.is_email_verified
        token["email"] = user.email
        return token

    def validate(self, attrs):
        # Note: Django's authenticate() already rejects is_active=False users
        # with a 401 before this point, so no separate is_active check is
        # needed here.
        data = super().validate(attrs)
        user = self.user

        if user.role == Role.PATIENT and not user.is_email_verified:
            raise serializers.ValidationError("Please verify your email before logging in.")

        data["role"] = user.role
        data["user_id"] = user.id
        return data


class PatientProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = PatientProfile
        fields = [
            "date_of_birth",
            "lmp_date",
            "edd_date",
            "blood_group",
            "emergency_contact_name",
            "emergency_contact_phone",
            "address",
            "profile_complete",
        ]
        read_only_fields = ["profile_complete"]

    def update(self, instance, validated_data):
        instance = super().update(instance, validated_data)
        instance.profile_complete = bool(instance.date_of_birth and instance.lmp_date)
        instance.save(update_fields=["profile_complete"])
        return instance


class DoctorProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = DoctorProfile
        fields = [
            "specialization",
            "license_number",
            "years_of_experience",
            "bio",
            "is_accepting_patients",
            "city",
            "area",
            "latitude",
            "longitude",
        ]


class MeSerializer(serializers.ModelSerializer):
    patient_profile = PatientProfileSerializer(read_only=True)
    doctor_profile = DoctorProfileSerializer(read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "role",
            "first_name",
            "last_name",
            "phone_number",
            "is_email_verified",
            "date_joined",
            "patient_profile",
            "doctor_profile",
        ]
        read_only_fields = fields


class MeUpdateSerializer(serializers.ModelSerializer):
    """Writable subset of MeSerializer — email/role/is_email_verified are never editable here."""

    class Meta:
        model = User
        fields = ["first_name", "last_name", "phone_number"]


class DoctorInviteSerializer(serializers.Serializer):
    email = serializers.EmailField()
    specialization = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError(
                "A user with this email already exists. Please use a different email address."
            )
        if DoctorInvite.objects.filter(email__iexact=value, status=DoctorInvite.Status.PENDING).exists():
            raise serializers.ValidationError(
                "An invite is already pending for this email. Please wait for it to be accepted or expire."
            )
        return value


class DoctorInviteAcceptSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp_code = serializers.CharField(min_length=6, max_length=6)
    password = serializers.CharField(write_only=True, validators=[validate_password])
    first_name = serializers.CharField(required=False, allow_blank=True, default="")
    last_name = serializers.CharField(required=False, allow_blank=True, default="")
    phone_number = serializers.CharField(required=False, allow_blank=True, default="")


class DoctorListSerializer(serializers.ModelSerializer):
    doctor_profile = DoctorProfileSerializer(read_only=True)
    distance_km = serializers.SerializerMethodField()
    average_rating = serializers.SerializerMethodField()
    total_ratings = serializers.SerializerMethodField()
    completed_appointments_count = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "phone_number",
            "is_active",
            "date_joined",
            "doctor_profile",
            "distance_km",
            "average_rating",
            "total_ratings",
            "completed_appointments_count",
        ]

    def get_average_rating(self, obj) -> float | None:
        from django.db.models import Avg

        result = obj.ratings_received.aggregate(avg=Avg("score"))["avg"]
        return round(result, 1) if result is not None else None

    def get_total_ratings(self, obj) -> int:
        return obj.ratings_received.count()

    def get_completed_appointments_count(self, obj) -> int:
        from apps.appointments.models import Appointment

        return Appointment.objects.filter(doctor=obj, status=Appointment.Status.COMPLETED).count()

    def get_distance_km(self, obj) -> float | None:
        # Only populated for the ?lat=&lng= "near me" search — see
        # DoctorViewSet.get_queryset, which annotates this attribute onto
        # each result. None (and therefore omitted-looking) otherwise.
        return getattr(obj, "distance_km", None)


class DoctorUpdateSerializer(serializers.ModelSerializer):
    doctor_profile = DoctorProfileSerializer(required=False)

    class Meta:
        model = User
        fields = ["is_active", "first_name", "last_name", "phone_number", "doctor_profile"]

    def update(self, instance, validated_data):
        profile_data = validated_data.pop("doctor_profile", None)
        instance = super().update(instance, validated_data)
        if profile_data:
            DoctorProfile.objects.filter(user=instance).update(**profile_data)
        return instance


class PatientSubscriptionSerializer(serializers.ModelSerializer):
    """
    Read-only everywhere it's used — is_paid/paid_at/etc. are only ever
    written server-side (accounts.services.mark_patient_paid), never
    accepted directly from a request body, so this never appears as a
    writable nested field on a patient-editable serializer (that would let
    a patient grant themselves free access via their own profile PATCH).
    """

    is_active = serializers.SerializerMethodField()
    days_remaining = serializers.SerializerMethodField()

    class Meta:
        model = PatientProfile
        fields = ["trial_ends_at", "is_paid", "paid_at", "payment_reference", "is_active", "days_remaining"]
        read_only_fields = fields

    def get_is_active(self, obj) -> bool:
        from apps.accounts.subscriptions import has_active_subscription

        return has_active_subscription(obj)

    def get_days_remaining(self, obj) -> int | None:
        if obj.is_paid or obj.trial_ends_at is None:
            return None
        from django.utils import timezone

        remaining = (obj.trial_ends_at - timezone.now()).days
        return max(remaining, 0)


class PatientListSerializer(serializers.ModelSerializer):
    patient_profile = PatientProfileSerializer(read_only=True)
    subscription = PatientSubscriptionSerializer(source="patient_profile", read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "phone_number",
            "is_active",
            "date_joined",
            "patient_profile",
            "subscription",
        ]


class PatientUpdateSerializer(serializers.ModelSerializer):
    patient_profile = PatientProfileSerializer(required=False)

    class Meta:
        model = User
        fields = ["is_active", "first_name", "last_name", "phone_number", "patient_profile"]

    def update(self, instance, validated_data):
        profile_data = validated_data.pop("patient_profile", None)
        instance = super().update(instance, validated_data)
        if profile_data:
            PatientProfile.objects.filter(user=instance).update(**profile_data)
        return instance


class PatientAssignDoctorSerializer(serializers.Serializer):
    doctor_id = serializers.PrimaryKeyRelatedField(queryset=User.objects.filter(role=Role.DOCTOR))


class MarkPatientPaidSerializer(serializers.Serializer):
    payment_reference = serializers.CharField(
        required=False, allow_blank=True, default="", help_text="e.g. a JazzCash/EasyPaisa transaction ID."
    )


class PlatformPaymentMethodSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlatformPaymentMethod
        fields = [
            "jazzcash_number",
            "jazzcash_account_title",
            "easypaisa_number",
            "easypaisa_account_title",
            "bank_name",
            "bank_account_title",
            "bank_account_number",
            "bank_iban",
            "updated_at",
        ]
        read_only_fields = ["updated_at"]


class MySubscriptionResponseSerializer(PatientSubscriptionSerializer):
    """Schema-only — adds payment_methods to PatientSubscriptionSerializer's fields for MySubscriptionView's response shape."""

    payment_methods = PlatformPaymentMethodSerializer(read_only=True)

    class Meta(PatientSubscriptionSerializer.Meta):
        fields = PatientSubscriptionSerializer.Meta.fields + ["payment_methods"]
        read_only_fields = fields
