from django.contrib import admin

from apps.appointments.models import Appointment, PatientDoctorAssignment


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ["id", "patient", "doctor", "appointment_type", "scheduled_at", "status"]
    list_filter = ["status", "appointment_type"]
    search_fields = ["patient__email", "doctor__email"]


@admin.register(PatientDoctorAssignment)
class PatientDoctorAssignmentAdmin(admin.ModelAdmin):
    list_display = ["patient", "doctor", "is_primary", "assigned_at"]
    list_filter = ["is_primary"]
    search_fields = ["patient__email", "doctor__email"]
