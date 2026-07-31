from unittest.mock import patch

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db


class TestRunScheduledTask:
    def test_missing_secret_is_forbidden(self, settings):
        settings.CRON_SECRET = "test-secret-value"
        client = APIClient()
        resp = client.post(reverse("run-scheduled-task", args=["medicine-reminders"]))
        assert resp.status_code == 403

    def test_wrong_secret_is_forbidden(self, settings):
        settings.CRON_SECRET = "test-secret-value"
        client = APIClient()
        resp = client.post(
            reverse("run-scheduled-task", args=["medicine-reminders"]), HTTP_X_CRON_SECRET="wrong"
        )
        assert resp.status_code == 403

    def test_unknown_task_name_404s_even_with_correct_secret(self, settings):
        settings.CRON_SECRET = "test-secret-value"
        client = APIClient()
        resp = client.post(
            reverse("run-scheduled-task", args=["not-a-real-task"]), HTTP_X_CRON_SECRET="test-secret-value"
        )
        assert resp.status_code == 404

    def test_correct_secret_executes_the_named_task(self, settings):
        settings.CRON_SECRET = "test-secret-value"
        client = APIClient()
        with patch("apps.notifications.tasks.send_medicine_reminders") as mock_task:
            resp = client.post(
                reverse("run-scheduled-task", args=["medicine-reminders"]),
                HTTP_X_CRON_SECRET="test-secret-value",
            )
        assert resp.status_code == 200
        mock_task.assert_called_once()

    def test_each_registered_task_name_dispatches_correctly(self, settings):
        settings.CRON_SECRET = "test-secret-value"
        client = APIClient()
        mapping = {
            "medicine-reminders": "apps.notifications.tasks.send_medicine_reminders",
            "appointment-reminders": "apps.notifications.tasks.send_appointment_reminders",
            "weekly-pregnancy-update": "apps.notifications.tasks.send_weekly_pregnancy_update",
            "cleanup-tokens": "apps.notifications.tasks.cleanup_expired_invites_and_tokens",
        }
        for task_name, dotted_path in mapping.items():
            with patch(dotted_path) as mock_task:
                resp = client.post(
                    reverse("run-scheduled-task", args=[task_name]), HTTP_X_CRON_SECRET="test-secret-value"
                )
            assert resp.status_code == 200, task_name
            mock_task.assert_called_once()

    def test_forbidden_when_cron_secret_unset(self, settings):
        """If CRON_SECRET is left blank (e.g. forgotten in prod env vars), the
        endpoint must fail closed, not silently accept an empty header value."""
        settings.CRON_SECRET = ""
        client = APIClient()
        resp = client.post(reverse("run-scheduled-task", args=["medicine-reminders"]), HTTP_X_CRON_SECRET="")
        assert resp.status_code == 403
