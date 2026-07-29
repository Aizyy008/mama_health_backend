from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

from apps.core.views import health_check

urlpatterns = [
    path("admin/", admin.site.urls),
    path("healthz/", health_check, name="health-check"),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
    path("api/v1/auth/", include("apps.accounts.auth_urls")),
    path("api/v1/accounts/", include("apps.accounts.urls")),
    path("api/v1/appointments/", include("apps.appointments.urls")),
    path("api/v1/health/", include("apps.health.urls")),
    path("api/v1/diet/", include("apps.diet.urls")),
    path("api/v1/medicines/", include("apps.medicines.urls")),
    path("api/v1/notifications/", include("apps.notifications.urls")),
    path("api/v1/hospitals/", include("apps.hospitals.urls")),
    path("api/v1/ai/", include("apps.ai_assistant.urls")),
    path("api/v1/reports/", include("apps.reports.urls")),
    path("api/v1/emergency/", include("apps.emergency.urls")),
]
