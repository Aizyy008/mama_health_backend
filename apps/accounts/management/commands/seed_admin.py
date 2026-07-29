import os

from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import User
from apps.core.constants import Role


class Command(BaseCommand):
    """
    Creates (or updates) the initial Admin account from env vars, for use in
    deploy scripts (e.g. Render's post-deploy step). Admin accounts are never
    created via an HTTP endpoint — this command and `createsuperuser` are the
    only ways to provision one.

    Reads SEED_ADMIN_EMAIL and SEED_ADMIN_PASSWORD from the environment.
    """

    help = "Create the initial Admin user from SEED_ADMIN_EMAIL / SEED_ADMIN_PASSWORD env vars."

    def handle(self, *args, **options):
        email = os.environ.get("SEED_ADMIN_EMAIL")
        password = os.environ.get("SEED_ADMIN_PASSWORD")
        if not email or not password:
            raise CommandError("SEED_ADMIN_EMAIL and SEED_ADMIN_PASSWORD must be set in the environment.")

        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                "role": Role.ADMIN,
                "is_staff": True,
                "is_superuser": True,
                "is_email_verified": True,
            },
        )
        user.set_password(password)
        user.role = Role.ADMIN
        user.is_staff = True
        user.is_superuser = True
        user.is_email_verified = True
        user.save()

        action = "Created" if created else "Updated"
        self.stdout.write(self.style.SUCCESS(f"{action} admin account: {email}"))
