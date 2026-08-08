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


def _task_registry():
    # Imported lazily (inside a function, not at module level) so that
    # apps.core — loaded first, before every other app — never has to import
    # apps.notifications/apps.accounts at Django startup time, only when this
    # view is actually hit.
    from apps.accounts.services import seed_dummy_doctors, seed_dummy_patient_appointment_and_sos
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
        "seed-dummy-patient-data": seed_dummy_patient_appointment_and_sos,
        # One-off, not on the GitHub Actions schedule — triggered manually
        # once for frontend-integration convenience. See docstring.
        "seed-dummy-doctors": seed_dummy_doctors,
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


@extend_schema(exclude=True)
@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([])
def reset_admin_password_emergency(request):
    """
    TEMPORARY — client accidentally changed the production admin password
    and there's no Render shell access (free tier) to fix it via
    createsuperuser/changepassword. Takes {email, new_password} in the
    body rather than a hardcoded value so the real password never ends up
    committed to source (this repo is public). Remove this view/URL once
    used — it's strictly more attack surface than the codebase needs
    long-term, even secret-gated.
    """
    provided_secret = request.headers.get("X-Cron-Secret", "")
    if not settings.CRON_SECRET or provided_secret != settings.CRON_SECRET:
        return Response({"detail": "Forbidden."}, status=status.HTTP_403_FORBIDDEN)

    from apps.accounts.models import User
    from apps.accounts.services import reset_admin_password

    email = request.data.get("email")
    new_password = request.data.get("new_password")
    if not email or not new_password:
        return Response({"detail": "email and new_password are both required."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        reset_admin_password(email=email, new_password=new_password)
    except User.DoesNotExist:
        return Response({"detail": "No admin account with that email."}, status=status.HTTP_404_NOT_FOUND)
    return Response({"detail": f"Password reset for {email}."})
