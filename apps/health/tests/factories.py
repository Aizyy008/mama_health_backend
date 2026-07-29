from datetime import date, timedelta

import factory
from django.utils import timezone

from apps.accounts.tests.factories import PatientUserFactory
from apps.health.models import BloodPressureReading, BloodSugarReading, WaterIntakeEntry


class BloodPressureReadingFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = BloodPressureReading

    patient = factory.SubFactory(PatientUserFactory)
    systolic = 120
    diastolic = 80
    recorded_at = factory.LazyFunction(timezone.now)


class BloodSugarReadingFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = BloodSugarReading

    patient = factory.SubFactory(PatientUserFactory)
    value_mg_dl = 95
    recorded_at = factory.LazyFunction(timezone.now)


class WaterIntakeEntryFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = WaterIntakeEntry

    patient = factory.SubFactory(PatientUserFactory)
    amount_ml = 250
    log_date = factory.LazyFunction(lambda: date.today())
