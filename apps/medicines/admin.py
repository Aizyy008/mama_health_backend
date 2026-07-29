from django.contrib import admin

from apps.medicines.models import MedicineIntakeLog, MedicineReminder


@admin.register(MedicineReminder)
class MedicineReminderAdmin(admin.ModelAdmin):
    list_display = ["patient", "medicine_name", "times_per_day", "is_active", "start_date", "end_date"]
    list_filter = ["is_active"]
    search_fields = ["patient__email", "medicine_name"]


@admin.register(MedicineIntakeLog)
class MedicineIntakeLogAdmin(admin.ModelAdmin):
    list_display = ["reminder", "scheduled_for", "status", "taken_at"]
    list_filter = ["status"]
