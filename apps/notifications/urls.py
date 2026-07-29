from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.notifications.views import BroadcastView, NotificationViewSet, SendDoctorMessageView

router = DefaultRouter()
router.register("", NotificationViewSet, basename="notification")

urlpatterns = [
    path("broadcast/", BroadcastView.as_view(), name="notification-broadcast"),
    path("send-to-patient/", SendDoctorMessageView.as_view(), name="notification-send-to-patient"),
    *router.urls,
]
