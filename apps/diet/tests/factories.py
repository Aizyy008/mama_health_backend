import factory

from apps.accounts.tests.factories import DoctorUserFactory, PatientUserFactory
from apps.diet.models import DietPlan


class DietPlanFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = DietPlan

    patient = factory.SubFactory(PatientUserFactory)
    created_by = factory.SubFactory(DoctorUserFactory)
    hydration_recommendation_ml = 2000
