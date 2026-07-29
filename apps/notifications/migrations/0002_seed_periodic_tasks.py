from django.db import migrations

TASK_NAMES = [
    "Send medicine reminders",
    "Send appointment reminders",
    "Send weekly pregnancy update",
    "Cleanup expired invites and tokens",
]


def seed_periodic_tasks(apps, schema_editor):
    IntervalSchedule = apps.get_model("django_celery_beat", "IntervalSchedule")
    CrontabSchedule = apps.get_model("django_celery_beat", "CrontabSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")

    five_min, _ = IntervalSchedule.objects.get_or_create(every=5, period="minutes")
    fifteen_min, _ = IntervalSchedule.objects.get_or_create(every=15, period="minutes")
    daily_8am, _ = CrontabSchedule.objects.get_or_create(
        minute="0", hour="8", day_of_week="*", day_of_month="*", month_of_year="*"
    )
    daily_2am, _ = CrontabSchedule.objects.get_or_create(
        minute="0", hour="2", day_of_week="*", day_of_month="*", month_of_year="*"
    )

    PeriodicTask.objects.get_or_create(
        name="Send medicine reminders",
        defaults={"task": "apps.notifications.tasks.send_medicine_reminders", "interval": five_min},
    )
    PeriodicTask.objects.get_or_create(
        name="Send appointment reminders",
        defaults={"task": "apps.notifications.tasks.send_appointment_reminders", "interval": fifteen_min},
    )
    PeriodicTask.objects.get_or_create(
        name="Send weekly pregnancy update",
        defaults={"task": "apps.notifications.tasks.send_weekly_pregnancy_update", "crontab": daily_8am},
    )
    PeriodicTask.objects.get_or_create(
        name="Cleanup expired invites and tokens",
        defaults={
            "task": "apps.notifications.tasks.cleanup_expired_invites_and_tokens",
            "crontab": daily_2am,
        },
    )


def remove_periodic_tasks(apps, schema_editor):
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    PeriodicTask.objects.filter(name__in=TASK_NAMES).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("notifications", "0001_initial"),
        ("django_celery_beat", "0019_alter_periodictasks_options"),
    ]

    operations = [migrations.RunPython(seed_periodic_tasks, remove_periodic_tasks)]
