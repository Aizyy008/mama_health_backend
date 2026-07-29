from django.db import models


class Role(models.TextChoices):
    PATIENT = "patient", "Patient"
    DOCTOR = "doctor", "Doctor"
    ADMIN = "admin", "Admin"
