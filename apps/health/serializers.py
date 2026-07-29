from rest_framework import serializers

from apps.core.serializers import PatientOwnedModelSerializer
from apps.health.models import (
    BabySizeReference,
    BloodPressureReading,
    BloodSugarReading,
    KickCountSession,
    KickEvent,
    SymptomLog,
    SymptomType,
    WaterIntakeEntry,
)


class BloodPressureReadingSerializer(PatientOwnedModelSerializer):
    class Meta:
        model = BloodPressureReading
        fields = [
            "id",
            "patient",
            "patient_id",
            "systolic",
            "diastolic",
            "pulse",
            "recorded_at",
            "notes",
            "created_at",
        ]
        read_only_fields = ["created_at"]


class BloodSugarReadingSerializer(PatientOwnedModelSerializer):
    class Meta:
        model = BloodSugarReading
        fields = [
            "id",
            "patient",
            "patient_id",
            "value_mg_dl",
            "reading_context",
            "recorded_at",
            "notes",
            "created_at",
        ]
        read_only_fields = ["created_at"]


class SymptomTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = SymptomType
        fields = ["id", "name"]


class SymptomLogSerializer(PatientOwnedModelSerializer):
    symptoms = SymptomTypeSerializer(many=True, read_only=True)
    symptom_ids = serializers.PrimaryKeyRelatedField(
        queryset=SymptomType.objects.all(), source="symptoms", many=True, required=False
    )

    class Meta:
        model = SymptomLog
        fields = [
            "id",
            "patient",
            "patient_id",
            "log_date",
            "symptoms",
            "symptom_ids",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]
        # DRF auto-adds a UniqueTogetherValidator from the model's
        # unique_together = ("patient", "log_date"), which would demand
        # "patient_id" be present in every payload — including a patient's
        # own self-serve requests, where it's intentionally omitted and
        # filled in later by perform_create(). The upsert in create() below
        # already makes DB-level uniqueness enforcement unnecessary here.
        validators = []

    def create(self, validated_data):
        symptoms = validated_data.pop("symptoms", [])
        instance, _ = SymptomLog.objects.update_or_create(
            patient=validated_data["patient"],
            log_date=validated_data["log_date"],
            defaults={"notes": validated_data.get("notes", "")},
        )
        instance.symptoms.set(symptoms)
        return instance


class WaterIntakeEntrySerializer(PatientOwnedModelSerializer):
    class Meta:
        model = WaterIntakeEntry
        fields = ["id", "patient", "patient_id", "amount_ml", "logged_at", "log_date", "created_at"]
        read_only_fields = ["logged_at", "created_at"]


class KickEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = KickEvent
        fields = ["id", "tapped_at"]
        read_only_fields = fields


class KickCountSessionSerializer(PatientOwnedModelSerializer):
    events = KickEventSerializer(many=True, read_only=True)

    class Meta:
        model = KickCountSession
        fields = [
            "id",
            "patient",
            "patient_id",
            "started_at",
            "ended_at",
            "kick_count",
            "log_date",
            "events",
            "created_at",
        ]
        read_only_fields = ["ended_at", "kick_count", "events", "created_at"]


class BabySizeReferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = BabySizeReference
        fields = ["week", "size_comparison", "length_cm", "weight_grams", "description"]


class PregnancyProgressSerializer(serializers.Serializer):
    lmp_date = serializers.DateField()
    edd_date = serializers.DateField()
    current_week = serializers.IntegerField()
    current_day = serializers.IntegerField()
    percent_complete = serializers.FloatField()
    trimester = serializers.IntegerField()
    days_remaining = serializers.IntegerField()
