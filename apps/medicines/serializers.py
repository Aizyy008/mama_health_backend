from django.utils import timezone
from rest_framework import serializers

from apps.core.serializers import PatientOwnedModelSerializer
from apps.medicines.models import MedicineIntakeLog, MedicineReminder


class MedicineReminderSerializer(PatientOwnedModelSerializer):
    class Meta:
        model = MedicineReminder
        fields = [
            "id",
            "patient",
            "patient_id",
            "medicine_name",
            "dosage",
            "times_per_day",
            "reminder_times",
            "start_date",
            "end_date",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]


class MedicineIntakeLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = MedicineIntakeLog
        fields = ["id", "reminder", "scheduled_for", "taken_at", "status", "created_at"]
        read_only_fields = fields


class LogIntakeSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=[MedicineIntakeLog.Status.TAKEN, MedicineIntakeLog.Status.SKIPPED]
    )
    scheduled_for = serializers.DateTimeField(required=False, default=timezone.now)
