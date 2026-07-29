from django.db import models

from apps.core.models import TimeStampedModel


class Notification(TimeStampedModel):
    class NotificationType(models.TextChoices):
        APPOINTMENT = "appointment", "Appointment"
        MEDICINE = "medicine", "Medicine"
        DIET = "diet", "Diet"
        DOCTOR_MESSAGE = "doctor_message", "Doctor message"
        WEEKLY_UPDATE = "weekly_update", "Weekly update"
        EMERGENCY = "emergency", "Emergency"
        BROADCAST = "broadcast", "Broadcast"

    recipient = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="notifications"
    )
    notification_type = models.CharField(max_length=30, choices=NotificationType.choices)
    title = models.CharField(max_length=200)
    body = models.TextField()
    data = models.JSONField(default=dict, blank=True)
    is_read = models.BooleanField(default=False)
    channel_push_sent = models.BooleanField(default=False)
    channel_whatsapp_sent = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]


class NotificationPreference(models.Model):
    user = models.OneToOneField(
        "accounts.User", on_delete=models.CASCADE, related_name="notification_preference"
    )
    push_enabled = models.BooleanField(default=True)
    whatsapp_enabled = models.BooleanField(default=True)
