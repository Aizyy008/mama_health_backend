from django.contrib import admin

from apps.health.models import (
    BabySizeReference,
    BloodPressureReading,
    BloodSugarReading,
    ExerciseVideo,
    KickCountSession,
    SurgicalProcedureRecord,
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


@admin.register(SurgicalProcedureRecord)
class SurgicalProcedureRecordAdmin(admin.ModelAdmin):
    list_display = ["patient", "procedure_name", "procedure_date", "hospital_name"]
    search_fields = ["patient__email", "procedure_name"]


@admin.register(ExerciseVideo)
class ExerciseVideoAdmin(admin.ModelAdmin):
    list_display = ["title", "category", "trimester", "duration_minutes"]
    list_filter = ["category", "trimester"]
    search_fields = ["title"]
