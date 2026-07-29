from django.urls import path

from apps.hospitals.views import NearbyHospitalsView

urlpatterns = [
    path("nearby/", NearbyHospitalsView.as_view(), name="hospitals-nearby"),
]
