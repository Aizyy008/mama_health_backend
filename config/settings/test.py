from .base import *  # noqa: F401,F403

DEBUG = False
SECRET_KEY = "test-secret-key"

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

# Throttling shares a process-lifetime cache keyed by (anonymous) IP, so
# unrelated tests in the same run would otherwise bleed into each other's
# rate limits (e.g. many auth-scoped POSTs across different test classes
# tripping the same 20/hour bucket). Nothing in the suite tests throttling
# itself, so it's disabled outright here rather than tuned up — a dedicated
# throttle test should override DEFAULT_THROTTLE_RATES per-test if ever added.
REST_FRAMEWORK = {**REST_FRAMEWORK, "DEFAULT_THROTTLE_CLASSES": []}
