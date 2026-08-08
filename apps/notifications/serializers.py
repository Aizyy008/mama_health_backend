from rest_framework import serializers

from apps.accounts.models import User
from apps.core.constants import Role
from apps.notifications.models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = [
            "id",
            "notification_type",
            "title",
            "body",
            "data",
            "is_read",
            "channel_push_sent",
            "channel_whatsapp_sent",
            "created_at",
        ]
        read_only_fields = fields


class BroadcastSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=200)
    body = serializers.CharField()
    target_role = serializers.ChoiceField(
        choices=[Role.PATIENT, Role.DOCTOR], required=False, allow_null=True, default=None
    )


class DoctorMessageSerializer(serializers.Serializer):
    patient_id = serializers.PrimaryKeyRelatedField(queryset=User.objects.filter(role=Role.PATIENT))
    title = serializers.CharField(max_length=200)
    body = serializers.CharField()


class UnreadCountSerializer(serializers.Serializer):
    unread_count = serializers.IntegerField()
