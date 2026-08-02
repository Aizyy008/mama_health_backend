from drf_spectacular.utils import OpenApiExample, OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import generics, permissions, status, viewsets
from rest_framework.decorators import action
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
    MeUpdateSerializer,
    PasswordChangeSerializer,
    PasswordForgotSerializer,
    PasswordResetSerializer,
    PasswordVerifyOTPResponseSerializer,
    PasswordVerifyOTPSerializer,
    PatientAssignDoctorSerializer,
    PatientListSerializer,
    PatientProfileSerializer,
    PatientUpdateSerializer,
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
        "cannot log in until `verify-email/` is called with the code from that email."
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
    summary="Verify email with a code",
    description=(
        "Consumes the 6-digit OTP code emailed to the patient on registration — a code, not a "
        "link, since patients are mobile-app-only and an emailed https:// link just opens a "
        "browser, not the app, without real deep-link setup. Only the most recently requested "
        "code is valid (requesting a new one via `resend-verification/` invalidates any previous "
        "unused code). Expires after `EMAIL_VERIFICATION_TOKEN_EXPIRY_HOURS` (default 48h)."
    ),
    responses={200: DetailResponseSerializer, 400: DetailResponseSerializer},
    examples=[
        OpenApiExample("Request", value={"email": "sara.ahmed@example.com", "otp_code": "482913"}, request_only=True),
        OpenApiExample("200 OK", value={"detail": "Email verified. You can now log in."}, response_only=True, status_codes=["200"]),
        OpenApiExample(
            "400 Invalid/expired code",
            value={"detail": "This code has expired. Please request a new one.", "errors": None},
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
            services.verify_email(
                email=serializer.validated_data["email"], otp_code=serializer.validated_data["otp_code"]
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"detail": "Email verified. You can now log in."})


@extend_schema(
    tags=["Auth"],
    summary="Resend the verification email",
    description=(
        "Re-issues a fresh verification code/email for an unverified account (invalidates any "
        "previous unused code). Always returns "
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
    summary="Request a password reset code (step 1 of 3)",
    description=(
        "Emails a 6-digit OTP code (expires after `PASSWORD_RESET_OTP_EXPIRY_MINUTES`, default 10 "
        "min) if the account exists. Always returns 200 with the same message regardless — does not "
        "leak account existence. Next step: `POST /auth/password/verify-otp/` with the code from "
        "the email."
    ),
    examples=[
        OpenApiExample("Request", value={"email": "sara.ahmed@example.com"}, request_only=True),
        OpenApiExample(
            "200 OK",
            value={"detail": "If that account exists, a password reset code has been sent."},
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
        return Response({"detail": "If that account exists, a password reset code has been sent."})


@extend_schema(
    tags=["Auth"],
    summary="Verify the password reset code (step 2 of 3)",
    description=(
        "Checks the emailed OTP code. On success, returns a `reset_token` to use with "
        "`POST /auth/password/reset/` (step 3) — the frontend doesn't need to resubmit the code "
        "again there. The code is single-use and only the most recently requested one is valid."
    ),
    responses={200: PasswordVerifyOTPResponseSerializer, 400: DetailResponseSerializer},
    examples=[
        OpenApiExample("Request", value={"email": "sara.ahmed@example.com", "otp_code": "482913"}, request_only=True),
        OpenApiExample(
            "200 OK",
            value={"detail": "Code verified.", "reset_token": "8fK2mZ...reset-token..."},
            response_only=True,
            status_codes=["200"],
        ),
        OpenApiExample(
            "400 Invalid/expired code",
            value={"detail": "This code has expired. Please request a new one.", "errors": None},
            response_only=True,
            status_codes=["400"],
        ),
    ],
)
class PasswordVerifyOTPView(generics.GenericAPIView):
    serializer_class = PasswordVerifyOTPSerializer
    permission_classes = [permissions.AllowAny]
    throttle_scope = "auth"

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            reset_token = services.verify_password_reset_otp(
                email=serializer.validated_data["email"],
                otp_code=serializer.validated_data["otp_code"],
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"detail": "Code verified.", "reset_token": reset_token})


@extend_schema(
    tags=["Auth"],
    summary="Reset password with token (step 3 of 3)",
    description="Consumes the single-use `reset_token` returned by `POST /auth/password/verify-otp/`. Token expires after `PASSWORD_RESET_TOKEN_EXPIRY_HOURS` (default 2h).",
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
        services.send_password_changed_email(request.user)
        return Response({"detail": "Password changed successfully."})


@extend_schema_view(
    get=extend_schema(
        tags=["Auth"],
        summary="Get the current user",
        description=(
            "Returns the authenticated user plus whichever of `patient_profile`/`doctor_profile` "
            "applies (the other is always `null`). Use `patient_profile.profile_complete` to decide "
            "whether to route a patient to the 'complete your profile' screen after login. Works for "
            "all three roles — for an Admin, both nested profiles are always `null`."
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
    ),
    patch=extend_schema(
        tags=["Auth"],
        summary="Update the current user's profile",
        description=(
            "Updates `first_name`/`last_name`/`phone_number` only — email, role, and verification "
            "status are never editable here. For patient-specific fields (LMP date, blood group, "
            "etc.) or doctor-specific fields (specialization, license), use "
            "`/accounts/me/patient-profile/` or `/accounts/me/doctor-profile/` instead. Works for "
            "all three roles, including Admin."
        ),
        examples=[
            OpenApiExample(
                "Request",
                value={"first_name": "Sara", "last_name": "Ahmed", "phone_number": "+923001234567"},
                request_only=True,
            ),
        ],
    ),
)
class MeView(generics.RetrieveUpdateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["get", "patch", "head", "options"]

    def get_serializer_class(self):
        if self.request.method == "PATCH":
            return MeUpdateSerializer
        return MeSerializer

    def get_object(self):
        return self.request.user

    def update(self, request, *args, **kwargs):
        super().update(request, *args, **kwargs)
        return Response(MeSerializer(request.user).data)


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
        "Public (no auth) — the doctor reaches this via the 6-digit OTP code emailed to them (a "
        "code, not a link, since the doctor app is mobile-only). Sets the doctor's password and "
        "activates the account. Unlike patient registration, this account is **immediately "
        "email-verified** (entering the invite code already proves ownership) and can log in "
        "right away."
    ),
    responses={201: DetailResponseSerializer, 400: DetailResponseSerializer},
    examples=[
        OpenApiExample(
            "Request",
            value={
                "email": "dr.ayesha@example.com",
                "otp_code": "482913",
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


_PATIENT_RESPONSE_EXAMPLE = {
    "id": 2,
    "email": "sara.ahmed@example.com",
    "first_name": "Sara",
    "last_name": "Ahmed",
    "phone_number": "+923001234567",
    "is_active": True,
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


@extend_schema_view(
    list=extend_schema(
        tags=["Accounts"],
        summary="List patients",
        description=(
            "Admin sees every patient (optionally narrowed with `?doctor_id=` to just that "
            "doctor's assigned patients). A doctor always sees only patients assigned to them "
            "(derived from `PatientDoctorAssignment`, created automatically the first time that "
            "patient books an appointment with them) — `?doctor_id=` has no effect for a doctor "
            "caller. Forbidden for patients."
        ),
        parameters=[
            OpenApiParameter(
                name="doctor_id",
                type=int,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Admin only: narrow the list to patients assigned to this doctor.",
            )
        ],
        examples=[
            OpenApiExample(
                "200 OK",
                value={"count": 1, "next": None, "previous": None, "results": [_PATIENT_RESPONSE_EXAMPLE]},
                response_only=True,
                status_codes=["200"],
            )
        ],
    ),
    retrieve=extend_schema(
        tags=["Accounts"],
        summary="Get a single patient",
        description="Same scoping as list — a doctor gets 404 for a patient not assigned to them.",
        examples=[OpenApiExample("200 OK", value=_PATIENT_RESPONSE_EXAMPLE, response_only=True, status_codes=["200"])],
    ),
    partial_update=extend_schema(
        tags=["Accounts"],
        summary="Update a patient (admin only)",
        description="Admin-only. Typically used to deactivate a patient (`is_active: false`) rather than delete — there is no delete endpoint, deactivation preserves their clinical history.",
        examples=[
            OpenApiExample("Request — deactivate", value={"is_active": False}, request_only=True),
            OpenApiExample("200 OK", value=_PATIENT_RESPONSE_EXAMPLE, response_only=True, status_codes=["200"]),
        ],
    ),
    create=extend_schema(exclude=True),
)
class PatientViewSet(viewsets.ModelViewSet):
    """Read: doctor (own assigned patients) or admin (all, or ?doctor_id=-scoped). Write: admin only."""

    queryset = User.objects.filter(role=Role.PATIENT).select_related("patient_profile")  # for schema introspection only
    http_method_names = ["get", "patch", "post", "head", "options"]
    permission_classes = [IsDoctorOrAdmin]

    def get_serializer_class(self):
        if self.action == "partial_update":
            return PatientUpdateSerializer
        return PatientListSerializer

    def get_permissions(self):
        if self.action in ("partial_update", "assign_doctor"):
            return [IsAdmin()]
        return [IsDoctorOrAdmin()]

    def get_queryset(self):
        qs = User.objects.filter(role=Role.PATIENT).select_related("patient_profile")
        user = self.request.user
        if user.role == Role.DOCTOR:
            from apps.appointments.models import PatientDoctorAssignment

            assigned_ids = PatientDoctorAssignment.objects.filter(doctor=user).values_list(
                "patient_id", flat=True
            )
            return qs.filter(id__in=assigned_ids)

        doctor_id = self.request.query_params.get("doctor_id")
        if doctor_id:
            from apps.appointments.models import PatientDoctorAssignment

            assigned_ids = PatientDoctorAssignment.objects.filter(doctor_id=doctor_id).values_list(
                "patient_id", flat=True
            )
            return qs.filter(id__in=assigned_ids)
        return qs

    def partial_update(self, request, *args, **kwargs):
        super().partial_update(request, *args, **kwargs)
        instance = self.get_object()
        return Response(PatientListSerializer(instance).data)

    def create(self, request, *args, **kwargs):
        # "post" is in http_method_names only for the assign-doctor action below;
        # patients are never created directly (they self-register via /auth/register/).
        from rest_framework.exceptions import MethodNotAllowed

        raise MethodNotAllowed("POST", detail="Patients cannot be created directly. Patients self-register via /auth/register/.")

    @extend_schema(
        tags=["Accounts"],
        summary="Assign a doctor to a patient (admin only)",
        description=(
            "Manually creates a `PatientDoctorAssignment` — the same access-control row that's "
            "normally created automatically when a patient books an appointment with a doctor. "
            "Idempotent (assigning the same doctor twice is a no-op). Use this to give a doctor "
            "access to a patient's records before any appointment exists."
        ),
        request=PatientAssignDoctorSerializer,
        responses={200: DetailResponseSerializer, 400: DetailResponseSerializer},
        examples=[
            OpenApiExample("Request", value={"doctor_id": 4}, request_only=True),
            OpenApiExample("200 OK", value={"detail": "Dr. Ayesha Malik assigned to this patient."}, response_only=True, status_codes=["200"]),
        ],
    )
    @action(detail=True, methods=["post"], url_path="assign-doctor", permission_classes=[IsAdmin])
    def assign_doctor(self, request, pk=None):
        from apps.appointments.models import PatientDoctorAssignment

        patient = self.get_object()
        serializer = PatientAssignDoctorSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        doctor = serializer.validated_data["doctor_id"]

        has_existing_assignment = PatientDoctorAssignment.objects.filter(patient=patient).exists()
        PatientDoctorAssignment.objects.get_or_create(
            patient=patient, doctor=doctor, defaults={"is_primary": not has_existing_assignment}
        )
        doctor_label = doctor.get_full_name() or doctor.email
        return Response({"detail": f"{doctor_label} assigned to this patient."})
