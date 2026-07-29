from drf_spectacular.utils import OpenApiExample, extend_schema, extend_schema_view
from rest_framework import generics, permissions, status, viewsets
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenBlacklistView, TokenObtainPairView, TokenRefreshView

from apps.accounts import services
from apps.accounts.models import DoctorProfile, PatientProfile, User
from apps.accounts.serializers import (
    DoctorInviteAcceptSerializer,
    DoctorInviteSerializer,
    DoctorListSerializer,
    DoctorProfileSerializer,
    DoctorUpdateSerializer,
    MamaHealthTokenObtainPairSerializer,
    MeSerializer,
    PasswordChangeSerializer,
    PasswordForgotSerializer,
    PasswordResetSerializer,
    PatientListSerializer,
    PatientProfileSerializer,
    RegisterSerializer,
    ResendVerificationSerializer,
    VerifyEmailSerializer,
)
from apps.core.constants import Role
from apps.core.permissions import IsAdmin, IsDoctor, IsDoctorOrAdmin, IsPatient
from apps.core.serializers import DetailResponseSerializer


@extend_schema(
    tags=["Auth"],
    summary="Register a new patient",
    description=(
        "Public, patient-only self-registration. Always creates a `role=patient` account "
        "regardless of anything else in the payload — doctors and admins are never created "
        "this way (see Doctor Invite / seed_admin). Sends a verification email; the account "
        "cannot log in until `verify-email/` is called with the token from that email."
    ),
    responses={201: DetailResponseSerializer, 400: DetailResponseSerializer},
    examples=[
        OpenApiExample(
            "Request",
            value={
                "email": "sara.ahmed@example.com",
                "password": "StrongPass123!",
                "first_name": "Sara",
                "last_name": "Ahmed",
                "phone_number": "+923001234567",
            },
            request_only=True,
        ),
        OpenApiExample(
            "201 Created",
            value={"detail": "Registration successful. Check your email to verify your account."},
            response_only=True,
            status_codes=["201"],
        ),
        OpenApiExample(
            "400 Email already registered",
            value={
                "detail": "An account with this email already exists. Please log in or use a different email.",
                "errors": {"email": ["An account with this email already exists. Please log in or use a different email."]},
            },
            response_only=True,
            status_codes=["400"],
        ),
    ],
)
class RegisterView(generics.GenericAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]
    throttle_scope = "auth"

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {"detail": "Registration successful. Check your email to verify your account."},
            status=status.HTTP_201_CREATED,
        )


@extend_schema(
    tags=["Auth"],
    summary="Verify email with token",
    description=(
        "Consumes the single-use token emailed to the patient on registration (link format: "
        "`{FRONTEND_URL}/verify-email?token=...`). The frontend reads `token` from that deep "
        "link's query string and POSTs it here. Token expires after "
        "`EMAIL_VERIFICATION_TOKEN_EXPIRY_HOURS` (default 48h)."
    ),
    responses={200: DetailResponseSerializer, 400: DetailResponseSerializer},
    examples=[
        OpenApiExample("Request", value={"token": "Pw5n22QuyiX8_7f-dQozm127jEjJ9Vz0gV7gsVH4qfE"}, request_only=True),
        OpenApiExample("200 OK", value={"detail": "Email verified. You can now log in."}, response_only=True, status_codes=["200"]),
        OpenApiExample(
            "400 Invalid/expired token",
            value={"detail": "Verification token has expired. Please request a new one.", "errors": None},
            response_only=True,
            status_codes=["400"],
        ),
    ],
)
class VerifyEmailView(generics.GenericAPIView):
    serializer_class = VerifyEmailSerializer
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            services.verify_email(serializer.validated_data["token"])
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"detail": "Email verified. You can now log in."})


@extend_schema(
    tags=["Auth"],
    summary="Resend the verification email",
    description=(
        "Re-issues a fresh verification token/email for an unverified account. Always returns "
        "200 with the same generic message whether or not the email exists/is already verified "
        "— this is intentional (does not leak account existence), so don't treat the response "
        "body as confirmation the email was actually sent."
    ),
    examples=[
        OpenApiExample("Request", value={"email": "sara.ahmed@example.com"}, request_only=True),
        OpenApiExample(
            "200 OK",
            value={"detail": "If that account exists and is unverified, a new email has been sent."},
            response_only=True,
            status_codes=["200"],
        ),
    ],
)
class ResendVerificationView(generics.GenericAPIView):
    serializer_class = ResendVerificationSerializer
    permission_classes = [permissions.AllowAny]
    throttle_scope = "auth"

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.resend_verification(serializer.validated_data["email"])
        return Response({"detail": "If that account exists and is unverified, a new email has been sent."})


@extend_schema(
    tags=["Auth"],
    summary="Login (obtain JWT access + refresh tokens)",
    description=(
        "Returns `access` (short-lived, default 30 min — send as `Authorization: Bearer <access>` "
        "on every subsequent request) and `refresh` (default 14 days — use at `/token/refresh/` to "
        "get a new access token without re-entering credentials). `role` and `user_id` are also "
        "echoed at the top level for convenience, and `role`/`is_email_verified`/`email` are embedded "
        "as claims inside the access token itself if you need to read them client-side without a "
        "round trip. Blocks unverified patients and deactivated accounts."
    ),
    responses={200: MamaHealthTokenObtainPairSerializer, 401: DetailResponseSerializer, 400: DetailResponseSerializer},
    examples=[
        OpenApiExample("Request", value={"email": "sara.ahmed@example.com", "password": "StrongPass123!"}, request_only=True),
        OpenApiExample(
            "200 OK",
            value={
                "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "access": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "role": "patient",
                "user_id": 2,
            },
            response_only=True,
            status_codes=["200"],
        ),
        OpenApiExample(
            "401 Wrong credentials",
            value={"detail": "Please enter a valid email and password."},
            response_only=True,
            status_codes=["401"],
        ),
        OpenApiExample(
            "400 Unverified email",
            value={"detail": "Please verify your email before logging in.", "errors": None},
            response_only=True,
            status_codes=["400"],
        ),
    ],
)
class MamaHealthTokenObtainPairView(TokenObtainPairView):
    serializer_class = MamaHealthTokenObtainPairSerializer
    throttle_scope = "auth"


@extend_schema(
    tags=["Auth"],
    summary="Refresh an access token",
    description="Exchange a still-valid `refresh` token for a new `access` token. Refresh tokens rotate on use (`ROTATE_REFRESH_TOKENS=True`) and the old one is blacklisted — always store and use the newest `refresh` value returned.",
    examples=[
        OpenApiExample("Request", value={"refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."}, request_only=True),
        OpenApiExample(
            "200 OK",
            value={"access": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...", "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."},
            response_only=True,
            status_codes=["200"],
        ),
    ],
)
class MamaHealthTokenRefreshView(TokenRefreshView):
    pass


@extend_schema(
    tags=["Auth"],
    summary="Logout (blacklist refresh token)",
    description="Blacklists the given refresh token so it can no longer be used to obtain new access tokens. The frontend should also discard both tokens locally. This does not invalidate an already-issued access token before its natural expiry (default 30 min).",
    examples=[
        OpenApiExample("Request", value={"refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."}, request_only=True),
        OpenApiExample("200 OK", value={}, response_only=True, status_codes=["200"]),
    ],
)
class LogoutView(TokenBlacklistView):
    pass


@extend_schema(
    tags=["Auth"],
    summary="Request a password reset email",
    description="Sends a reset link (`{FRONTEND_URL}/reset-password?token=...`) if the email exists. Always returns 200 with the same message regardless — does not leak account existence.",
    examples=[
        OpenApiExample("Request", value={"email": "sara.ahmed@example.com"}, request_only=True),
        OpenApiExample(
            "200 OK",
            value={"detail": "If that account exists, a password reset email has been sent."},
            response_only=True,
            status_codes=["200"],
        ),
    ],
)
class PasswordForgotView(generics.GenericAPIView):
    serializer_class = PasswordForgotSerializer
    permission_classes = [permissions.AllowAny]
    throttle_scope = "auth"

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.request_password_reset(serializer.validated_data["email"])
        return Response({"detail": "If that account exists, a password reset email has been sent."})


@extend_schema(
    tags=["Auth"],
    summary="Reset password with token",
    description="Consumes the single-use token from the password-reset email. Token expires after `PASSWORD_RESET_TOKEN_EXPIRY_HOURS` (default 2h).",
    responses={200: DetailResponseSerializer, 400: DetailResponseSerializer},
    examples=[
        OpenApiExample(
            "Request",
            value={"token": "8fK2mZ...reset-token...", "new_password": "NewStrongPass123!"},
            request_only=True,
        ),
        OpenApiExample("200 OK", value={"detail": "Password reset successful. You can now log in."}, response_only=True, status_codes=["200"]),
        OpenApiExample(
            "400 Invalid/expired token",
            value={"detail": "Reset token has expired. Please request a new one.", "errors": None},
            response_only=True,
            status_codes=["400"],
        ),
    ],
)
class PasswordResetView(generics.GenericAPIView):
    serializer_class = PasswordResetSerializer
    permission_classes = [permissions.AllowAny]
    throttle_scope = "auth"

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            services.reset_password(
                token=serializer.validated_data["token"],
                new_password=serializer.validated_data["new_password"],
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"detail": "Password reset successful. You can now log in."})


@extend_schema(
    tags=["Auth"],
    summary="Change password (authenticated)",
    description="Requires the current password. Authenticated via the normal `Authorization: Bearer <access>` header — no separate token.",
    responses={200: DetailResponseSerializer, 400: DetailResponseSerializer},
    examples=[
        OpenApiExample(
            "Request",
            value={"old_password": "StrongPass123!", "new_password": "EvenStrongerPass456!"},
            request_only=True,
        ),
        OpenApiExample("200 OK", value={"detail": "Password changed successfully."}, response_only=True, status_codes=["200"]),
        OpenApiExample(
            "400 Wrong old password",
            value={
                "detail": "The old password you entered is incorrect. Please try again.",
                "errors": {"old_password": ["The old password you entered is incorrect. Please try again."]},
            },
            response_only=True,
            status_codes=["400"],
        ),
    ],
)
class PasswordChangeView(generics.GenericAPIView):
    serializer_class = PasswordChangeSerializer
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = self.get_serializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        request.user.set_password(serializer.validated_data["new_password"])
        request.user.save(update_fields=["password"])
        return Response({"detail": "Password changed successfully."})


@extend_schema(
    tags=["Auth"],
    summary="Get the current user",
    description=(
        "Returns the authenticated user plus whichever of `patient_profile`/`doctor_profile` "
        "applies (the other is always `null`). Use `patient_profile.profile_complete` to decide "
        "whether to route a patient to the 'complete your profile' screen after login."
    ),
    examples=[
        OpenApiExample(
            "200 OK — patient",
            value={
                "id": 2,
                "email": "sara.ahmed@example.com",
                "role": "patient",
                "first_name": "Sara",
                "last_name": "Ahmed",
                "phone_number": "+923001234567",
                "is_email_verified": True,
                "date_joined": "2026-01-15T10:30:00Z",
                "patient_profile": {
                    "date_of_birth": "1995-06-20",
                    "lmp_date": "2026-05-01",
                    "edd_date": None,
                    "blood_group": "O+",
                    "emergency_contact_name": "Ahmed Khan",
                    "emergency_contact_phone": "+923001112222",
                    "address": "House 12, Street 5, Karachi",
                    "profile_complete": True,
                },
                "doctor_profile": None,
            },
            response_only=True,
            status_codes=["200"],
        ),
    ],
)
class MeView(generics.RetrieveAPIView):
    serializer_class = MeSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user


@extend_schema(
    tags=["Accounts"],
    summary="View/update my patient profile",
    description="Patient-only. `GET` returns the current profile (auto-created empty on first access); `PATCH` updates any subset of fields. `profile_complete` is read-only and server-computed (true once both `date_of_birth` and `lmp_date` are set) — don't attempt to set it directly.",
    examples=[
        OpenApiExample(
            "PATCH request",
            value={
                "date_of_birth": "1995-06-20",
                "lmp_date": "2026-05-01",
                "blood_group": "O+",
                "emergency_contact_name": "Ahmed Khan",
                "emergency_contact_phone": "+923001112222",
                "address": "House 12, Street 5, Karachi",
            },
            request_only=True,
        ),
        OpenApiExample(
            "200 OK",
            value={
                "date_of_birth": "1995-06-20",
                "lmp_date": "2026-05-01",
                "edd_date": None,
                "blood_group": "O+",
                "emergency_contact_name": "Ahmed Khan",
                "emergency_contact_phone": "+923001112222",
                "address": "House 12, Street 5, Karachi",
                "profile_complete": True,
            },
            response_only=True,
            status_codes=["200"],
        ),
    ],
)
class MyPatientProfileView(generics.RetrieveUpdateAPIView):
    serializer_class = PatientProfileSerializer
    permission_classes = [IsPatient]

    def get_object(self):
        profile, _ = PatientProfile.objects.get_or_create(user=self.request.user)
        return profile


@extend_schema(
    tags=["Accounts"],
    summary="View/update my doctor profile",
    description="Doctor-only. `GET` returns the current profile (auto-created empty on first access); `PATCH` updates any subset of fields.",
    examples=[
        OpenApiExample(
            "PATCH request",
            value={
                "specialization": "OB-GYN",
                "license_number": "PMC-12345",
                "years_of_experience": 8,
                "bio": "Board-certified obstetrician with 8 years of experience in high-risk pregnancies.",
                "is_accepting_patients": True,
            },
            request_only=True,
        ),
        OpenApiExample(
            "200 OK",
            value={
                "specialization": "OB-GYN",
                "license_number": "PMC-12345",
                "years_of_experience": 8,
                "bio": "Board-certified obstetrician with 8 years of experience in high-risk pregnancies.",
                "is_accepting_patients": True,
            },
            response_only=True,
            status_codes=["200"],
        ),
    ],
)
class MyDoctorProfileView(generics.RetrieveUpdateAPIView):
    serializer_class = DoctorProfileSerializer
    permission_classes = [IsDoctor]

    def get_object(self):
        profile, _ = DoctorProfile.objects.get_or_create(user=self.request.user)
        return profile


@extend_schema(
    tags=["Accounts"],
    summary="Invite a doctor (admin only)",
    description=(
        "Admin-only. Creates a pending `DoctorInvite` and emails an accept link "
        "(`{FRONTEND_URL}/doctor-invite?token=...`) to `email`. This is the **only** way a doctor "
        "account gets created — there is no public doctor self-registration. The invite expires "
        "after `DOCTOR_INVITE_EXPIRY_DAYS` (default 7 days) if never accepted."
    ),
    responses={201: DetailResponseSerializer, 400: DetailResponseSerializer},
    examples=[
        OpenApiExample("Request", value={"email": "dr.ayesha@example.com", "specialization": "OB-GYN"}, request_only=True),
        OpenApiExample("201 Created", value={"detail": "Invite sent."}, response_only=True, status_codes=["201"]),
        OpenApiExample(
            "400 Already exists / pending",
            value={
                "detail": "A user with this email already exists. Please use a different email address.",
                "errors": {"email": ["A user with this email already exists. Please use a different email address."]},
            },
            response_only=True,
            status_codes=["400"],
        ),
    ],
)
class DoctorInviteView(generics.GenericAPIView):
    serializer_class = DoctorInviteSerializer
    permission_classes = [IsAdmin]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.invite_doctor(invited_by=request.user, **serializer.validated_data)
        return Response(
            {"detail": "Invite sent."},
            status=status.HTTP_201_CREATED,
        )


@extend_schema(
    tags=["Accounts"],
    summary="Accept a doctor invite",
    description=(
        "Public (no auth) — the doctor reaches this via the emailed invite link's token. Sets the "
        "doctor's password and activates the account. Unlike patient registration, this account is "
        "**immediately email-verified** (accepting the invite email already proves ownership) and "
        "can log in right away."
    ),
    responses={201: DetailResponseSerializer, 400: DetailResponseSerializer},
    examples=[
        OpenApiExample(
            "Request",
            value={
                "token": "8fK2mZ...invite-token...",
                "password": "DoctorPass123!",
                "first_name": "Ayesha",
                "last_name": "Malik",
                "phone_number": "+923009876543",
            },
            request_only=True,
        ),
        OpenApiExample(
            "201 Created",
            value={"detail": "Account activated. You can now log in."},
            response_only=True,
            status_codes=["201"],
        ),
        OpenApiExample(
            "400 Invalid/expired invite",
            value={"detail": "This invite has expired. Ask an admin to send a new one.", "errors": None},
            response_only=True,
            status_codes=["400"],
        ),
    ],
)
class DoctorInviteAcceptView(generics.GenericAPIView):
    serializer_class = DoctorInviteAcceptSerializer
    permission_classes = [permissions.AllowAny]
    throttle_scope = "auth"

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            services.accept_doctor_invite(**serializer.validated_data)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"detail": "Account activated. You can now log in."}, status=status.HTTP_201_CREATED)


@extend_schema_view(
    list=extend_schema(
        tags=["Accounts"],
        summary="List doctors",
        description="Any authenticated role (patient/doctor/admin) — e.g. a patient browsing doctors to book an appointment with. Paginated.",
        examples=[
            OpenApiExample(
                "200 OK",
                value={
                    "count": 1,
                    "next": None,
                    "previous": None,
                    "results": [
                        {
                            "id": 4,
                            "email": "dr.ayesha@example.com",
                            "first_name": "Ayesha",
                            "last_name": "Malik",
                            "phone_number": "+923009876543",
                            "is_active": True,
                            "date_joined": "2026-01-10T09:00:00Z",
                            "doctor_profile": {
                                "specialization": "OB-GYN",
                                "license_number": "PMC-12345",
                                "years_of_experience": 8,
                                "bio": "Board-certified obstetrician.",
                                "is_accepting_patients": True,
                            },
                        }
                    ],
                },
                response_only=True,
                status_codes=["200"],
            )
        ],
    ),
    retrieve=extend_schema(
        tags=["Accounts"],
        summary="Get a single doctor",
        examples=[
            OpenApiExample(
                "200 OK",
                value={
                    "id": 4,
                    "email": "dr.ayesha@example.com",
                    "first_name": "Ayesha",
                    "last_name": "Malik",
                    "phone_number": "+923009876543",
                    "is_active": True,
                    "date_joined": "2026-01-10T09:00:00Z",
                    "doctor_profile": {
                        "specialization": "OB-GYN",
                        "license_number": "PMC-12345",
                        "years_of_experience": 8,
                        "bio": "Board-certified obstetrician.",
                        "is_accepting_patients": True,
                    },
                },
                response_only=True,
                status_codes=["200"],
            )
        ],
    ),
    partial_update=extend_schema(
        tags=["Accounts"],
        summary="Update a doctor (admin only)",
        description="Admin-only. Typically used to deactivate a doctor (`is_active: false`) rather than delete — there is no delete endpoint, deactivation preserves their history.",
        examples=[
            OpenApiExample("Request — deactivate", value={"is_active": False}, request_only=True),
            OpenApiExample("200 OK", value={"is_active": False, "first_name": "Ayesha", "last_name": "Malik", "phone_number": "+923009876543", "doctor_profile": {"specialization": "OB-GYN", "license_number": "PMC-12345", "years_of_experience": 8, "bio": "Board-certified obstetrician.", "is_accepting_patients": True}}, response_only=True, status_codes=["200"]),
        ],
    ),
)
class DoctorViewSet(viewsets.ModelViewSet):
    """Read: any authenticated user (e.g. patients browsing doctors to book with). Write: admin only."""

    http_method_names = ["get", "patch", "head", "options"]
    queryset = User.objects.filter(role=Role.DOCTOR).select_related("doctor_profile")
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.action in ("update", "partial_update"):
            return DoctorUpdateSerializer
        return DoctorListSerializer

    def get_permissions(self):
        if self.action in ("update", "partial_update"):
            return [IsAdmin()]
        return [permissions.IsAuthenticated()]


@extend_schema(
    tags=["Accounts"],
    summary="List patients",
    description="Admin sees every patient. A doctor sees only patients assigned to them (derived from `PatientDoctorAssignment`, created automatically the first time that patient books an appointment with them). Forbidden for patients.",
    examples=[
        OpenApiExample(
            "200 OK",
            value={
                "count": 1,
                "next": None,
                "previous": None,
                "results": [
                    {
                        "id": 2,
                        "email": "sara.ahmed@example.com",
                        "first_name": "Sara",
                        "last_name": "Ahmed",
                        "phone_number": "+923001234567",
                        "date_joined": "2026-01-15T10:30:00Z",
                        "patient_profile": {
                            "date_of_birth": "1995-06-20",
                            "lmp_date": "2026-05-01",
                            "edd_date": None,
                            "blood_group": "O+",
                            "emergency_contact_name": "Ahmed Khan",
                            "emergency_contact_phone": "+923001112222",
                            "address": "House 12, Street 5, Karachi",
                            "profile_complete": True,
                        },
                    }
                ],
            },
            response_only=True,
            status_codes=["200"],
        )
    ],
)
class PatientListView(generics.ListAPIView):
    """Admin sees all patients; a doctor sees only patients assigned to them."""

    serializer_class = PatientListSerializer
    permission_classes = [IsDoctorOrAdmin]

    def get_queryset(self):
        qs = User.objects.filter(role=Role.PATIENT).select_related("patient_profile")
        user = self.request.user
        if user.role == Role.DOCTOR:
            from apps.appointments.models import PatientDoctorAssignment

            assigned_ids = PatientDoctorAssignment.objects.filter(doctor=user).values_list(
                "patient_id", flat=True
            )
            qs = qs.filter(id__in=assigned_ids)
        return qs
