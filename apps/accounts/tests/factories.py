from datetime import timedelta

import factory
from django.utils import timezone

from apps.accounts.models import DoctorProfile, PatientProfile, User
from apps.core.constants import Role


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User
        skip_postgeneration_save = True

    email = factory.Sequence(lambda n: f"user{n}@example.com")
    first_name = "Test"
    last_name = "User"
    is_active = True
    is_email_verified = True

    @factory.post_generation
    def password(self, create, extracted, **kwargs):
        self.set_password(extracted or "TestPass123!")
        if create:
            self.save()


class PatientUserFactory(UserFactory):
    role = Role.PATIENT

    @factory.post_generation
    def profile(self, create, extracted, **kwargs):
        # Defaults to an active trial (matches a freshly registered patient
        # via accounts.services.register_patient) so tests don't need to
        # think about the subscription soft lock unless they're explicitly
        # testing it — see TestSubscriptionSoftLock.
        if create:
            PatientProfile.objects.get_or_create(
                user=self, defaults={"trial_ends_at": timezone.now() + timedelta(days=7)}
            )


class DoctorUserFactory(UserFactory):
    role = Role.DOCTOR

    @factory.post_generation
    def profile(self, create, extracted, **kwargs):
        if create:
            DoctorProfile.objects.get_or_create(user=self)


class AdminUserFactory(UserFactory):
    role = Role.ADMIN
    is_staff = True
    is_superuser = True
