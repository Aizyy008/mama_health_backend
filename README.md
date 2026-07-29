# Mama Health — Backend

Django REST API for the Mama Health pregnancy care platform. Serves the Patient, Doctor, and Admin (Flutter Web) clients over a single versioned API, documented via Swagger/OpenAPI (drf-spectacular).

## Stack

Django 5 + DRF, PostgreSQL, Redis (cache + Celery broker), Celery/Celery Beat for background jobs, JWT auth (simplejwt), deployed on Render.

## Local setup

Postgres and Redis run in Docker; the Django app itself runs natively via `manage.py runserver` (not containerized).

```bash
# 1. Start Postgres + Redis
docker compose up -d

# 2. Create and activate a virtualenv
python3 -m venv venv
source venv/bin/activate
pip install -r requirements/dev.txt

# 3. Configure environment
cp .env.example .env   # already done if you're reading this after initial setup

# 4. Migrate and run
python manage.py migrate
python manage.py runserver

# 5. Create an admin account (never via HTTP — see apps/accounts/management/commands/seed_admin.py)
python manage.py createsuperuser
```

- API docs (Swagger UI): http://127.0.0.1:8000/api/docs/
- ReDoc: http://127.0.0.1:8000/api/redoc/
- OpenAPI schema: http://127.0.0.1:8000/api/schema/
- Django admin: http://127.0.0.1:8000/admin/
- Health check: http://127.0.0.1:8000/healthz/

## Running tests

```bash
DJANGO_SETTINGS_MODULE=config.settings.test pytest
```

## Project layout

- `config/` — settings (`dev.py` / `prod.py` / `test.py`), root URLs, Celery app
- `apps/` — one Django app per bounded context (`accounts`, `appointments`, `health`, `diet`, `medicines`, `notifications`, `hospitals`, `ai_assistant`, `reports`, `emergency`, `core`)
- `render.yaml` — Render deployment topology (web + Celery worker + Celery beat + managed Postgres/Redis)

See `.env.example` for every configuration variable, including third-party integrations (AI provider, WhatsApp Business API, Firebase Cloud Messaging, Google Places) which are all optional at boot — the app runs end-to-end without them via null/no-op adapters, and real credentials can be dropped in later with zero code changes.
