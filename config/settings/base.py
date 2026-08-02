"""
Base settings shared by all environments. Environment-specific settings
(dev.py / prod.py / test.py) import * from here and override as needed.
"""
from datetime import timedelta
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
env_file = BASE_DIR / ".env"
if env_file.exists():
    environ.Env.read_env(str(env_file))

SECRET_KEY = env.str("SECRET_KEY", default="django-insecure-change-me-in-env")
DEBUG = env.bool("DEBUG", default=False)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "drf_spectacular",
    "corsheaders",
    "django_celery_beat",
]

LOCAL_APPS = [
    "apps.core",
    "apps.accounts",
    "apps.appointments",
    "apps.health",
    "apps.diet",
    "apps.medicines",
    "apps.notifications",
    "apps.hospitals",
    "apps.ai_assistant",
    "apps.reports",
    "apps.emergency",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default="postgres://mama_health:mama_health@localhost:5432/mama_health",
    )
}
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DB_CONN_MAX_AGE", default=60)

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------------------
# Internationalization
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = env.str("TIME_ZONE", default="UTC")
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Static files
# ---------------------------------------------------------------------------
# No media/file uploads in v1 — all three Flutter clients use icon
# placeholders for profile pictures rather than uploaded images, so there is
# no user-uploaded media to store (and therefore no S3/Cloudinary need).
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# DRF / JWT / OpenAPI
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.StandardResultsSetPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_RENDERER_CLASSES": (
        "rest_framework.renderers.JSONRenderer",
    ),
    "DEFAULT_THROTTLE_CLASSES": (
        # ScopedRateThrottle only acts on views that declare throttle_scope
        # (auth, ai_assistant, hospitals — tighter, endpoint-specific limits).
        # UserRateThrottle/AnonRateThrottle apply everywhere as a generous
        # baseline safety net so no endpoint is completely unthrottled.
        "rest_framework.throttling.ScopedRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.AnonRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "auth": "20/hour",
        "ai_assistant": "20/hour",
        "hospitals": "60/hour",
        "user": "2000/day",
        "anon": "100/day",
    },
    "EXCEPTION_HANDLER": "apps.core.exceptions.custom_exception_handler",
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=env.int("ACCESS_TOKEN_LIFETIME_MINUTES", default=30)),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=env.int("REFRESH_TOKEN_LIFETIME_DAYS", default=14)),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
    "TOKEN_OBTAIN_SERIALIZER": "apps.accounts.serializers.MamaHealthTokenObtainPairSerializer",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Mama Health API",
    "DESCRIPTION": (
        "REST API for the Mama Health pregnancy care platform. "
        "Serves the Patient, Doctor, and Admin (Flutter Web) clients."
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SCHEMA_PATH_PREFIX": "/api/v1/",
    "SWAGGER_UI_SETTINGS": {"persistAuthorization": True},
    "COMPONENT_SPLIT_REQUEST": True,
    "SORT_OPERATIONS": False,
    "TAGS": [
        {"name": "Auth", "description": "Registration, login, email verification, password reset."},
        {"name": "Accounts", "description": "User profiles and doctor provisioning (admin-managed)."},
        {"name": "Appointments", "description": "Appointment booking and doctor-patient assignment."},
        {"name": "Health", "description": "Vitals, health tracker, pregnancy progress."},
        {"name": "Diet", "description": "Doctor-authored diet plans."},
        {"name": "Medicines", "description": "Medicine reminders and intake logs."},
        {"name": "Notifications", "description": "In-app notifications and admin broadcasts."},
        {"name": "Hospitals", "description": "Nearby hospital search (Google Places proxy)."},
        {"name": "AI Assistant", "description": "AI pregnancy assistant chat."},
        {"name": "Reports", "description": "Aggregated reports and admin system statistics."},
        {"name": "Emergency", "description": "Emergency SOS."},
    ],
}

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
# CORS_ALLOW_ALL_ORIGINS is a deliberate temporary escape hatch for active
# frontend integration, when the exact origin(s) calling the API aren't
# pinned down yet (e.g. Flutter Web dev builds on a random local port).
# Tighten to CORS_ALLOWED_ORIGINS once real origins are known — see
# DEPLOYMENT.md. Reasonably low-risk even wide open: this API is JWT
# bearer-token auth (Authorization header set explicitly by app code), not
# cookie/session auth, so a browser won't silently attach credentials to a
# cross-origin request the way it would with cookies.
CORS_ALLOW_ALL_ORIGINS = env.bool("CORS_ALLOW_ALL_ORIGINS", default=False)
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])
CORS_ALLOW_CREDENTIALS = True

# ---------------------------------------------------------------------------
# Cache (Redis, optional) & Celery
# ---------------------------------------------------------------------------
# Redis is entirely optional. If REDIS_URL isn't set, the cache falls back to
# local-memory (fine for the hospitals-search cache on a single free-tier
# instance) and Celery has no broker to talk to — which is also fine, because
# CELERY_TASK_ALWAYS_EAGER (see below) means task.delay() calls execute
# synchronously in-process and never touch a broker at all. This lets the
# whole system run on just a web service + a database, no paid worker or
# managed Redis required. Set REDIS_URL (and CELERY_TASK_ALWAYS_EAGER=False)
# later if/when a real Celery worker is added.
REDIS_URL = env.str("REDIS_URL", default="")

if REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": REDIS_URL,
            "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
            "KEY_PREFIX": "mama_health",
        }
    }
    CELERY_BROKER_URL = REDIS_URL
else:
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
    CELERY_BROKER_URL = "memory://"

CELERY_RESULT_BACKEND = None
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"
# Default True: without a separate worker process, .delay() should run the
# task inline immediately rather than queuing it somewhere nothing consumes.
# dev/test explicitly reaffirm this; prod.py can override to False once a
# real worker + REDIS_URL exist.
CELERY_TASK_ALWAYS_EAGER = env.bool("CELERY_TASK_ALWAYS_EAGER", default=True)

# Shared secret for the /internal/tasks/<name>/ endpoints that an external
# scheduler (GitHub Actions cron, in the absence of a paid Celery Beat
# worker) calls to trigger the periodic jobs. Required in prod — see
# config/settings/prod.py.
CRON_SECRET = env.str("CRON_SECRET", default="")

# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------
EMAIL_BACKEND = env.str("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = env.str("EMAIL_HOST", default="")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_HOST_USER = env.str("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env.str("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
DEFAULT_FROM_EMAIL = env.str("DEFAULT_FROM_EMAIL", default="Mama Health <no-reply@mamahealth.app>")

# Used to build links inside verification/reset/invite emails (Flutter deep
# link base or a minimal static confirmation page — there is no server-rendered UI).
FRONTEND_URL = env.str("FRONTEND_URL", default="https://app.mamahealth.example")

# ---------------------------------------------------------------------------
# Token / invite expiry windows
# ---------------------------------------------------------------------------
EMAIL_VERIFICATION_TOKEN_EXPIRY_HOURS = env.int("EMAIL_VERIFICATION_TOKEN_EXPIRY_HOURS", default=48)
PASSWORD_RESET_TOKEN_EXPIRY_HOURS = env.int("PASSWORD_RESET_TOKEN_EXPIRY_HOURS", default=2)
PASSWORD_RESET_OTP_EXPIRY_MINUTES = env.int("PASSWORD_RESET_OTP_EXPIRY_MINUTES", default=10)
DOCTOR_INVITE_EXPIRY_DAYS = env.int("DOCTOR_INVITE_EXPIRY_DAYS", default=7)

# ---------------------------------------------------------------------------
# Pluggable third-party integrations — all credentials optional at boot.
# Each app's adapter factory checks these for presence and falls back to a
# null/no-op adapter when unset, so the system runs end-to-end before the
# client supplies real keys.
# ---------------------------------------------------------------------------
AI_PROVIDER = env.str("AI_PROVIDER", default="")  # "openai" | "gemini" | ""
AI_API_KEY = env.str("AI_API_KEY", default="")
AI_MODEL_NAME = env.str("AI_MODEL_NAME", default="")

WHATSAPP_API_TOKEN = env.str("WHATSAPP_API_TOKEN", default="")
WHATSAPP_PHONE_NUMBER_ID = env.str("WHATSAPP_PHONE_NUMBER_ID", default="")

FCM_CREDENTIALS_JSON = env.str("FCM_CREDENTIALS_JSON", default="")

GOOGLE_PLACES_API_KEY = env.str("GOOGLE_PLACES_API_KEY", default="")
HOSPITAL_CACHE_TTL_SECONDS = env.int("HOSPITAL_CACHE_TTL_SECONDS", default=3600)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {"format": "[{levelname}] {asctime} {name}: {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "verbose"},
    },
    "root": {"handlers": ["console"], "level": env.str("LOG_LEVEL", default="INFO")},
    "loggers": {
        "django": {"handlers": ["console"], "level": env.str("LOG_LEVEL", default="INFO"), "propagate": False},
    },
}
