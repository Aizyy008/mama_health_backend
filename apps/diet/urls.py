from rest_framework.routers import DefaultRouter

from apps.diet.views import DietPlanViewSet

router = DefaultRouter()
router.register("plans", DietPlanViewSet, basename="diet-plan")

urlpatterns = router.urls
