from django.contrib import admin

from apps.notifications.models import Notification, NotificationPreference


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ["recipient", "notification_type", "title", "is_read", "created_at"]
    list_filter = ["notification_type", "is_read"]
    search_fields = ["recipient__email", "title"]


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = ["user", "push_enabled", "whatsapp_enabled"]
