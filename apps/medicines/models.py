from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel


class MedicineReminder(TimeStampedModel):
    patient = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="medicine_reminders"
    )
    medicine_name = models.CharField(max_length=150)
    dosage = models.CharField(max_length=100, blank=True)
    times_per_day = models.PositiveSmallIntegerField(default=1)
    reminder_times = models.JSONField(default=list, blank=True, help_text='e.g. ["08:00", "20:00"]')
    start_date = models.DateField(default=timezone.localdate)
    end_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-created_at"]


class MedicineIntakeLog(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        TAKEN = "taken", "Taken"
        SKIPPED = "skipped", "Skipped"

    reminder = models.ForeignKey(MedicineReminder, on_delete=models.CASCADE, related_name="intake_logs")
    scheduled_for = models.DateTimeField()
    taken_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)

    class Meta:
        ordering = ["-scheduled_for"]
