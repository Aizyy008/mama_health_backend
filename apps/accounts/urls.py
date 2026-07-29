from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.accounts import views

router = DefaultRouter()
router.register("doctors", views.DoctorViewSet, basename="doctor")

urlpatterns = [
    path("doctors/invite/", views.DoctorInviteView.as_view(), name="doctor-invite"),
    path("doctors/invite/accept/", views.DoctorInviteAcceptView.as_view(), name="doctor-invite-accept"),
    path("patients/", views.PatientListView.as_view(), name="patient-list"),
    path("me/patient-profile/", views.MyPatientProfileView.as_view(), name="my-patient-profile"),
    path("me/doctor-profile/", views.MyDoctorProfileView.as_view(), name="my-doctor-profile"),
    *router.urls,
]
