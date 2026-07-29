from rest_framework.routers import DefaultRouter

from apps.medicines.views import MedicineIntakeLogViewSet, MedicineReminderViewSet

router = DefaultRouter()
router.register("reminders", MedicineReminderViewSet, basename="medicine-reminder")
router.register("intake-logs", MedicineIntakeLogViewSet, basename="medicine-intake-log")

urlpatterns = router.urls
