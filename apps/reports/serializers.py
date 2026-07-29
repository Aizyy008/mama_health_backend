from rest_framework import serializers

from apps.appointments.serializers import AppointmentSerializer
from apps.diet.serializers import DietPlanSerializer
from apps.health.serializers import (
    BloodPressureReadingSerializer,
    BloodSugarReadingSerializer,
    PregnancyProgressSerializer,
    SymptomLogSerializer,
)


class MedicineAdherenceSerializer(serializers.Serializer):
    taken = serializers.IntegerField()
    skipped = serializers.IntegerField()
    pending = serializers.IntegerField()


class PatientSummaryReportSerializer(serializers.Serializer):
    pregnancy_progress = PregnancyProgressSerializer(allow_null=True)
    latest_blood_pressure = BloodPressureReadingSerializer(allow_null=True)
    latest_blood_sugar = BloodSugarReadingSerializer(allow_null=True)
    active_diet_plan = DietPlanSerializer(allow_null=True)
    upcoming_appointments = AppointmentSerializer(many=True)
    recent_symptoms = SymptomLogSerializer(many=True)
    medicine_adherence = MedicineAdherenceSerializer()


class AdminStatsSerializer(serializers.Serializer):
    total_patients = serializers.IntegerField()
    total_doctors = serializers.IntegerField()
    total_appointments = serializers.IntegerField()
    appointments_this_month = serializers.IntegerField()
    active_sos_events = serializers.IntegerField()
    new_patients_this_week = serializers.IntegerField()
