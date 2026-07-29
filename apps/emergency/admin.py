from django.contrib import admin

from apps.emergency.models import EmergencySOSEvent


@admin.register(EmergencySOSEvent)
class EmergencySOSEventAdmin(admin.ModelAdmin):
    list_display = ["patient", "status", "created_at", "resolved_at"]
    list_filter = ["status"]
    search_fields = ["patient__email"]
