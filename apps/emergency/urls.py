from rest_framework.routers import DefaultRouter

from apps.emergency.views import EmergencySOSViewSet

router = DefaultRouter()
router.register("sos", EmergencySOSViewSet, basename="emergency-sos")

urlpatterns = router.urls
