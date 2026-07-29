from django.db import models

from apps.core.constants import Role
from apps.core.models import TimeStampedModel


class Appointment(TimeStampedModel):
    class AppointmentType(models.TextChoices):
        IN_PERSON = "in_person", "In person"
        VIDEO_CONSULTATION = "video_consultation", "Video consultation"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CONFIRMED = "confirmed", "Confirmed"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"
        NO_SHOW = "no_show", "No show"

    patient = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="appointments",
        limit_choices_to={"role": Role.PATIENT},
    )
    doctor = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="doctor_appointments",
        limit_choices_to={"role": Role.DOCTOR},
    )
    appointment_type = models.CharField(
        max_length=20, choices=AppointmentType.choices, default=AppointmentType.IN_PERSON
    )
    scheduled_at = models.DateTimeField()
    duration_minutes = models.PositiveIntegerField(default=30)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    # Not auto-generated in v1 — no live video SDK integration. Filled in
    # manually (or by a future integration) once a video_consultation
    # appointment is confirmed.
    meeting_link = models.URLField(blank=True)
    reason = models.TextField(blank=True)
    doctor_notes = models.TextField(blank=True)
    cancelled_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    cancellation_reason = models.TextField(blank=True)

    class Meta:
        ordering = ["-scheduled_at"]

    def __str__(self):
        return f"Appointment<{self.patient_id} with {self.doctor_id} @ {self.scheduled_at}>"


class PatientDoctorAssignment(models.Model):
    """
    Derived access-control record: created automatically the first time a
    patient books an appointment with a doctor. Every clinical app (health,
    diet, medicines, reports) checks this table to decide whether a doctor
    may see a given patient's data, instead of re-deriving from Appointment
    history each time.
    """

    patient = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="assigned_doctors"
    )
    doctor = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="assigned_patients"
    )
    assigned_at = models.DateTimeField(auto_now_add=True)
    is_primary = models.BooleanField(default=False)

    class Meta:
        unique_together = ("patient", "doctor")

    def __str__(self):
        return f"PatientDoctorAssignment<patient={self.patient_id}, doctor={self.doctor_id}>"
