import factory

from apps.accounts.tests.factories import PatientUserFactory
from apps.medicines.models import MedicineReminder


class MedicineReminderFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = MedicineReminder

    patient = factory.SubFactory(PatientUserFactory)
    medicine_name = "Folic Acid"
    dosage = "5mg"
    times_per_day = 1
    reminder_times = ["09:00"]
