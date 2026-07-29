from rest_framework.routers import DefaultRouter

from apps.ai_assistant.views import ChatSessionViewSet

router = DefaultRouter()
router.register("sessions", ChatSessionViewSet, basename="chat-session")

urlpatterns = router.urls
