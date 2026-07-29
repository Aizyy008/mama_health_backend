import pytest
from django.urls import reverse
from rest_framework import status

from apps.accounts.tests.factories import DoctorUserFactory, PatientUserFactory
from apps.appointments.models import PatientDoctorAssignment
from apps.diet.models import DietPlan
from apps.diet.tests.factories import DietPlanFactory

pytestmark = pytest.mark.django_db


class TestDietPlanWritePermissions:
    def test_patient_cannot_create_own_diet_plan(self, patient_client, patient_user):
        resp = patient_client.post(
            reverse("diet-plan-list"), {"patient_id": patient_user.id, "notes": "test"}, format="json"
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_unassigned_doctor_cannot_create_plan_for_patient(self, doctor_client):
        patient = PatientUserFactory()
        resp = doctor_client.post(
            reverse("diet-plan-list"), {"patient_id": patient.id, "notes": "test"}, format="json"
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_assigned_doctor_can_create_plan_with_nested_meals_and_foods(self, doctor_client, doctor_user):
        patient = PatientUserFactory()
        PatientDoctorAssignment.objects.create(patient=patient, doctor=doctor_user)
        resp = doctor_client.post(
            reverse("diet-plan-list"),
            {
                "patient_id": patient.id,
                "hydration_recommendation_ml": 2500,
                "meals": [{"meal_type": "breakfast", "description": "Oatmeal and fruit"}],
                "foods_to_avoid": [{"food_name": "Raw fish", "reason": "Food safety"}],
            },
            format="json",
        )
        assert resp.status_code == status.HTTP_201_CREATED
        assert resp.data["is_active"] is True
        assert len(resp.data["meals"]) == 1
        assert len(resp.data["foods_to_avoid"]) == 1
        assert resp.data["created_by"]["id"] == doctor_user.id


class TestOnlyOneActivePlan:
    def test_creating_new_plan_deactivates_previous(self, doctor_client, doctor_user):
        patient = PatientUserFactory()
        PatientDoctorAssignment.objects.create(patient=patient, doctor=doctor_user)
        first = DietPlanFactory(patient=patient, created_by=doctor_user, is_active=True)

        resp = doctor_client.post(
            reverse("diet-plan-list"), {"patient_id": patient.id, "notes": "second plan"}, format="json"
        )
        assert resp.status_code == status.HTTP_201_CREATED

        first.refresh_from_db()
        assert first.is_active is False
        assert DietPlan.objects.filter(patient=patient, is_active=True).count() == 1

    def test_history_is_preserved_not_deleted(self, patient_client, patient_user):
        DietPlanFactory(patient=patient_user, is_active=False)
        DietPlanFactory(patient=patient_user, is_active=True)
        resp = patient_client.get(reverse("diet-plan-list"))
        assert resp.data["count"] == 2


class TestActivePlanEndpoint:
    def test_patient_gets_own_active_plan(self, patient_client, patient_user):
        DietPlanFactory(patient=patient_user, is_active=False)
        active = DietPlanFactory(patient=patient_user, is_active=True)
        resp = patient_client.get(reverse("diet-plan-active"))
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["id"] == active.id

    def test_404_when_no_active_plan(self, patient_client):
        resp = patient_client.get(reverse("diet-plan-active"))
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_doctor_requires_patient_id(self, doctor_client):
        resp = doctor_client.get(reverse("diet-plan-active"))
        assert resp.status_code == status.HTTP_400_BAD_REQUEST


class TestReadScoping:
    def test_patient_cannot_see_others_plans(self, patient_client, patient_user):
        DietPlanFactory(patient=patient_user)
        DietPlanFactory()
        resp = patient_client.get(reverse("diet-plan-list"))
        assert resp.data["count"] == 1

    def test_unassigned_doctor_sees_nothing(self, doctor_client):
        DietPlanFactory()
        resp = doctor_client.get(reverse("diet-plan-list"))
        assert resp.data["count"] == 0


class TestUpdate:
    def test_patient_cannot_update_plan(self, patient_client, patient_user):
        plan = DietPlanFactory(patient=patient_user)
        resp = patient_client.patch(
            reverse("diet-plan-detail", args=[plan.id]), {"notes": "hacked"}, format="json"
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_assigned_doctor_can_update_plan(self, doctor_client, doctor_user):
        patient = PatientUserFactory()
        PatientDoctorAssignment.objects.create(patient=patient, doctor=doctor_user)
        plan = DietPlanFactory(patient=patient, created_by=doctor_user)
        resp = doctor_client.patch(
            reverse("diet-plan-detail", args=[plan.id]), {"notes": "updated notes"}, format="json"
        )
        assert resp.status_code == status.HTTP_200_OK
        plan.refresh_from_db()
        assert plan.notes == "updated notes"
