from rest_framework import serializers

from apps.accounts.serializers import BriefUserSerializer
from apps.emergency import services
from apps.emergency.models import EmergencySOSEvent


class EmergencySOSEventSerializer(serializers.ModelSerializer):
    patient = BriefUserSerializer(read_only=True)

    class Meta:
        model = EmergencySOSEvent
        fields = ["id", "patient", "latitude", "longitude", "status", "resolved_at", "notes", "created_at"]
        read_only_fields = ["patient", "status", "resolved_at", "created_at"]

    def create(self, validated_data):
        return services.trigger_sos(**validated_data)


class ResolveSOSSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=[EmergencySOSEvent.Status.RESOLVED, EmergencySOSEvent.Status.FALSE_ALARM]
    )
