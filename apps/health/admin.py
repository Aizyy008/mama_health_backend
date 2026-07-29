from django.contrib import admin

from apps.health.models import (
    BabySizeReference,
    BloodPressureReading,
    BloodSugarReading,
    KickCountSession,
    SymptomLog,
    SymptomType,
    WaterIntakeEntry,
)


@admin.register(BloodPressureReading)
class BloodPressureReadingAdmin(admin.ModelAdmin):
    list_display = ["patient", "systolic", "diastolic", "pulse", "recorded_at"]
    search_fields = ["patient__email"]


@admin.register(BloodSugarReading)
class BloodSugarReadingAdmin(admin.ModelAdmin):
    list_display = ["patient", "value_mg_dl", "reading_context", "recorded_at"]
    search_fields = ["patient__email"]


@admin.register(SymptomType)
class SymptomTypeAdmin(admin.ModelAdmin):
    search_fields = ["name"]


@admin.register(SymptomLog)
class SymptomLogAdmin(admin.ModelAdmin):
    list_display = ["patient", "log_date"]
    search_fields = ["patient__email"]


@admin.register(WaterIntakeEntry)
class WaterIntakeEntryAdmin(admin.ModelAdmin):
    list_display = ["patient", "amount_ml", "log_date"]
    search_fields = ["patient__email"]


@admin.register(KickCountSession)
class KickCountSessionAdmin(admin.ModelAdmin):
    list_display = ["patient", "log_date", "kick_count", "started_at", "ended_at"]
    search_fields = ["patient__email"]


@admin.register(BabySizeReference)
class BabySizeReferenceAdmin(admin.ModelAdmin):
    list_display = ["week", "size_comparison", "length_cm", "weight_grams"]
