import os

from django.conf import settings
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


@extend_schema(exclude=True)
@api_view(["GET"])
@permission_classes([AllowAny])
def health_check(request):
    return Response({"status": "ok"})


@extend_schema(exclude=True)
@api_view(["GET"])
@permission_classes([AllowAny])
@throttle_classes([])
def debug_cors(request):
    """TEMPORARY diagnostic — remove once the live CORS env var mystery is resolved."""
    provided_secret = request.headers.get("X-Cron-Secret", "")
    if not settings.CRON_SECRET or provided_secret != settings.CRON_SECRET:
        return Response({"detail": "Forbidden."}, status=status.HTTP_403_FORBIDDEN)
    return Response(
        {
            "settings_CORS_ALLOW_ALL_ORIGINS": settings.CORS_ALLOW_ALL_ORIGINS,
            "settings_CORS_ALLOWED_ORIGINS": settings.CORS_ALLOWED_ORIGINS,
            "os_environ_raw": os.environ.get("CORS_ALLOW_ALL_ORIGINS"),
            "django_settings_module": os.environ.get("DJANGO_SETTINGS_MODULE"),
        }
    )


def _task_registry():
    # Imported lazily (inside a function, not at module level) so that
    # apps.core — loaded first, before every other app — never has to import
    # apps.notifications at Django startup time, only when this view is
    # actually hit.
    from apps.notifications.tasks import (
        cleanup_expired_invites_and_tokens,
        send_appointment_reminders,
        send_medicine_reminders,
        send_weekly_pregnancy_update,
    )

    return {
        "medicine-reminders": send_medicine_reminders,
        "appointment-reminders": send_appointment_reminders,
        "weekly-pregnancy-update": send_weekly_pregnancy_update,
        "cleanup-tokens": cleanup_expired_invites_and_tokens,
    }


@extend_schema(exclude=True)
@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([])  # called every few minutes by the cron workflow — the
# default AnonRateThrottle (100/day) would otherwise block it by mid-morning;
# the shared-secret check is this endpoint's actual access control.
def run_scheduled_task(request, task_name):
    """
    Triggers one of the periodic notification jobs synchronously. Not part
    of the public API (excluded from Swagger, lives outside /api/v1/) — this
    exists specifically so a free external scheduler (a GitHub Actions cron
    workflow) can replace a paid, always-on Celery Beat worker. Protected by
    a shared secret header, not user auth, since the caller is an automation
    rather than a logged-in user. Calling a @shared_task-decorated function
    directly (not via .delay()) runs it immediately in-process — no broker
    involved either way.
    """
    provided_secret = request.headers.get("X-Cron-Secret", "")
    if not settings.CRON_SECRET or provided_secret != settings.CRON_SECRET:
        return Response({"detail": "Forbidden."}, status=status.HTTP_403_FORBIDDEN)

    task = _task_registry().get(task_name)
    if task is None:
        return Response({"detail": "Unknown task."}, status=status.HTTP_404_NOT_FOUND)

    task()
    return Response({"detail": f"Task '{task_name}' executed."})
