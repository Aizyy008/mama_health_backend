import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.tests.factories import AdminUserFactory, DoctorUserFactory, PatientUserFactory


def _authed_client(user):
    client = APIClient()
    access = str(RefreshToken.for_user(user).access_token)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return client


@pytest.fixture
def patient_user(db):
    return PatientUserFactory()


@pytest.fixture
def doctor_user(db):
    return DoctorUserFactory()


@pytest.fixture
def admin_user(db):
    return AdminUserFactory()


@pytest.fixture
def patient_client(patient_user):
    return _authed_client(patient_user)


@pytest.fixture
def doctor_client(doctor_user):
    return _authed_client(doctor_user)


@pytest.fixture
def admin_client(admin_user):
    return _authed_client(admin_user)


@pytest.fixture
def anon_client():
    return APIClient()
