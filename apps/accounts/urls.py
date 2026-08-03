from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.accounts import views

router = DefaultRouter()
router.register("doctors", views.DoctorViewSet, basename="doctor")
router.register("patients", views.PatientViewSet, basename="patient")

urlpatterns = [
    path("doctors/invite/", views.DoctorInviteView.as_view(), name="doctor-invite"),
    path("doctors/invite/accept/", views.DoctorInviteAcceptView.as_view(), name="doctor-invite-accept"),
    path("me/patient-profile/", views.MyPatientProfileView.as_view(), name="my-patient-profile"),
    path("me/doctor-profile/", views.MyDoctorProfileView.as_view(), name="my-doctor-profile"),
    path("me/subscription/", views.MySubscriptionView.as_view(), name="my-subscription"),
    path("payment-methods/", views.PaymentMethodView.as_view(), name="payment-methods"),
    *router.urls,
]
