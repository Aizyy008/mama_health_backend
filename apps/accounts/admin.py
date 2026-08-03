from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from apps.accounts.models import (
    DoctorInvite,
    DoctorProfile,
    EmailVerificationToken,
    PasswordResetToken,
    PatientProfile,
    PlatformPaymentMethod,
    User,
)


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    ordering = ["email"]
    list_display = ["email", "role", "is_email_verified", "is_active", "is_staff"]
    list_filter = ["role", "is_email_verified", "is_active"]
    search_fields = ["email", "phone_number"]
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Role", {"fields": ("role", "phone_number", "is_email_verified", "fcm_device_token")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("email", "role", "password1", "password2")}),
    )


admin.site.register(PatientProfile)
admin.site.register(DoctorProfile)
admin.site.register(DoctorInvite)
admin.site.register(EmailVerificationToken)
admin.site.register(PasswordResetToken)
admin.site.register(PlatformPaymentMethod)
