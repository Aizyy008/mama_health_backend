from rest_framework import serializers

from apps.accounts.serializers import DoctorListSerializer, PatientListSerializer
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


class TrimesterDistributionSerializer(serializers.Serializer):
    trimester_1 = serializers.IntegerField()
    trimester_2 = serializers.IntegerField()
    trimester_3 = serializers.IntegerField()
    unknown = serializers.IntegerField(help_text="Patients with a profile but no LMP date set yet.")


class RecentActivitySerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=["patient_registered", "appointment_booked", "sos_triggered"])
    description = serializers.CharField()
    timestamp = serializers.DateTimeField()


class AdminStatsSerializer(serializers.Serializer):
    total_patients = serializers.IntegerField()
    total_doctors = serializers.IntegerField()
    total_appointments = serializers.IntegerField()
    appointments_this_month = serializers.IntegerField()
    today_appointments = serializers.IntegerField()
    active_sos_events = serializers.IntegerField()
    new_patients_this_week = serializers.IntegerField()
    trimester_distribution = TrimesterDistributionSerializer()
    recent_activities = RecentActivitySerializer(many=True)
    patients_paid = serializers.IntegerField()
    patients_on_trial = serializers.IntegerField()
    patients_trial_expired = serializers.IntegerField()


class SearchResultsSerializer(serializers.Serializer):
    doctors = DoctorListSerializer(many=True)
    patients = PatientListSerializer(many=True)
    appointments = AppointmentSerializer(many=True)
