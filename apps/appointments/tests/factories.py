from datetime import timedelta

import factory
from django.utils import timezone

from apps.appointments.models import Appointment
from apps.accounts.tests.factories import DoctorUserFactory, PatientUserFactory


class AppointmentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Appointment

    patient = factory.SubFactory(PatientUserFactory)
    doctor = factory.SubFactory(DoctorUserFactory)
    appointment_type = Appointment.AppointmentType.IN_PERSON
    scheduled_at = factory.LazyFunction(lambda: timezone.now() + timedelta(days=1))
    reason = "Routine checkup"
