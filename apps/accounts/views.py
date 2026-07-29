from drf_spectacular.utils import extend_schema, extend_schema_view
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


@extend_schema(tags=["Auth"])
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


@extend_schema(tags=["Auth"])
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


@extend_schema(tags=["Auth"])
class ResendVerificationView(generics.GenericAPIView):
    serializer_class = ResendVerificationSerializer
    permission_classes = [permissions.AllowAny]
    throttle_scope = "auth"

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.resend_verification(serializer.validated_data["email"])
        return Response({"detail": "If that account exists and is unverified, a new email has been sent."})


@extend_schema(tags=["Auth"])
class MamaHealthTokenObtainPairView(TokenObtainPairView):
    serializer_class = MamaHealthTokenObtainPairSerializer
    throttle_scope = "auth"


@extend_schema(tags=["Auth"])
class MamaHealthTokenRefreshView(TokenRefreshView):
    pass


@extend_schema(tags=["Auth"])
class LogoutView(TokenBlacklistView):
    pass


@extend_schema(tags=["Auth"])
class PasswordForgotView(generics.GenericAPIView):
    serializer_class = PasswordForgotSerializer
    permission_classes = [permissions.AllowAny]
    throttle_scope = "auth"

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.request_password_reset(serializer.validated_data["email"])
        return Response({"detail": "If that account exists, a password reset email has been sent."})


@extend_schema(tags=["Auth"])
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


@extend_schema(tags=["Auth"])
class PasswordChangeView(generics.GenericAPIView):
    serializer_class = PasswordChangeSerializer
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = self.get_serializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        request.user.set_password(serializer.validated_data["new_password"])
        request.user.save(update_fields=["password"])
        return Response({"detail": "Password changed successfully."})


@extend_schema(tags=["Auth"])
class MeView(generics.RetrieveAPIView):
    serializer_class = MeSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user


@extend_schema(tags=["Accounts"])
class MyPatientProfileView(generics.RetrieveUpdateAPIView):
    serializer_class = PatientProfileSerializer
    permission_classes = [IsPatient]

    def get_object(self):
        profile, _ = PatientProfile.objects.get_or_create(user=self.request.user)
        return profile


@extend_schema(tags=["Accounts"])
class MyDoctorProfileView(generics.RetrieveUpdateAPIView):
    serializer_class = DoctorProfileSerializer
    permission_classes = [IsDoctor]

    def get_object(self):
        profile, _ = DoctorProfile.objects.get_or_create(user=self.request.user)
        return profile


@extend_schema(tags=["Accounts"])
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


@extend_schema(tags=["Accounts"])
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
    list=extend_schema(tags=["Accounts"]),
    retrieve=extend_schema(tags=["Accounts"]),
    partial_update=extend_schema(tags=["Accounts"]),
    update=extend_schema(tags=["Accounts"]),
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


@extend_schema(tags=["Accounts"])
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
