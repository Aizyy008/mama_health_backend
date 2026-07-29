from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel


class BloodPressureReading(TimeStampedModel):
    patient = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="bp_readings")
    systolic = models.PositiveSmallIntegerField()
    diastolic = models.PositiveSmallIntegerField()
    pulse = models.PositiveSmallIntegerField(null=True, blank=True)
    recorded_at = models.DateTimeField(default=timezone.now)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-recorded_at"]


class BloodSugarReading(TimeStampedModel):
    class Context(models.TextChoices):
        FASTING = "fasting", "Fasting"
        POST_MEAL = "post_meal", "Post-meal"
        RANDOM = "random", "Random"

    patient = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="sugar_readings")
    value_mg_dl = models.PositiveSmallIntegerField()
    reading_context = models.CharField(max_length=20, choices=Context.choices, default=Context.RANDOM)
    recorded_at = models.DateTimeField(default=timezone.now)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-recorded_at"]


class SymptomType(models.Model):
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class SymptomLog(TimeStampedModel):
    patient = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="symptom_logs")
    log_date = models.DateField(db_index=True, default=timezone.localdate)
    symptoms = models.ManyToManyField(SymptomType, blank=True, related_name="logs")
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-log_date"]
        unique_together = ("patient", "log_date")


class WaterIntakeEntry(TimeStampedModel):
    patient = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="water_entries")
    amount_ml = models.PositiveIntegerField()
    logged_at = models.DateTimeField(default=timezone.now)
    log_date = models.DateField(db_index=True, default=timezone.localdate)

    class Meta:
        ordering = ["-logged_at"]


class KickCountSession(TimeStampedModel):
    patient = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="kick_sessions")
    started_at = models.DateTimeField(default=timezone.now)
    ended_at = models.DateTimeField(null=True, blank=True)
    kick_count = models.PositiveIntegerField(default=0)
    log_date = models.DateField(db_index=True, default=timezone.localdate)

    class Meta:
        ordering = ["-started_at"]


class KickEvent(TimeStampedModel):
    session = models.ForeignKey(KickCountSession, on_delete=models.CASCADE, related_name="events")
    tapped_at = models.DateTimeField(default=timezone.now)


class BabySizeReference(models.Model):
    """Static reference data (seeded via data migration), not per-patient."""

    week = models.PositiveSmallIntegerField(unique=True)
    size_comparison = models.CharField(max_length=100)
    length_cm = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    weight_grams = models.DecimalField(max_digits=6, decimal_places=1, null=True, blank=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["week"]

    def __str__(self):
        return f"Week {self.week}: {self.size_comparison}"


class SurgicalProcedureRecord(TimeStampedModel):
    """Patient-owned, self-logged record of past/scheduled procedures
    (e.g. C-section, cerclage) — same access pattern as BP/blood sugar."""

    patient = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="surgical_procedures"
    )
    procedure_name = models.CharField(max_length=200)
    procedure_date = models.DateField()
    hospital_name = models.CharField(max_length=200, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-procedure_date"]


class ExerciseVideo(models.Model):
    """Admin-managed reference table of external video links (YouTube/Vimeo/
    etc.) — no video files are hosted by this project (no media storage)."""

    class Category(models.TextChoices):
        EXERCISE = "exercise", "Exercise"
        BREATHING = "breathing", "Breathing"

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=20, choices=Category.choices)
    video_url = models.URLField()
    duration_minutes = models.PositiveIntegerField(null=True, blank=True)
    trimester = models.PositiveSmallIntegerField(null=True, blank=True, help_text="1, 2, or 3 — optional")

    class Meta:
        ordering = ["category", "title"]

    def __str__(self):
        return self.title
