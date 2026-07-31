# Mama Health — Backend

Django REST API for the Mama Health pregnancy care platform. Serves the Patient, Doctor, and Admin (Flutter Web) clients over a single versioned API, documented via Swagger/OpenAPI (drf-spectacular).

## Stack

Django 5 + DRF, PostgreSQL, JWT auth (simplejwt). Deployed at $0/month: Render free web service + Neon free Postgres, no managed Redis or dedicated worker — background jobs run inline, and scheduled reminders are triggered by a free GitHub Actions cron instead of Celery Beat. See `CLAUDE.md`'s "Zero-cost deployment" section for the full rationale and runbook. Redis remains fully supported (cache + real Celery broker) for local dev and as a drop-in upgrade path if a paid worker is ever added later.

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

# 6. (Optional, dev only) Seed ready-to-use test accounts + sample data
python manage.py seed_test_data
```

- API docs (Swagger UI): http://127.0.0.1:8000/api/docs/
- ReDoc: http://127.0.0.1:8000/api/redoc/
- OpenAPI schema (live): http://127.0.0.1:8000/api/schema/
- Django admin: http://127.0.0.1:8000/admin/
- Health check: http://127.0.0.1:8000/healthz/

Background jobs run inline by default (`CELERY_TASK_ALWAYS_EAGER=True`) — no separate process needed for normal local dev. To test real async behavior against local Redis instead, set `CELERY_TASK_ALWAYS_EAGER=False` in `.env` and run in separate terminals:
```bash
celery -A config worker -l info
celery -A config beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler
```

## API handoff for the Flutter team

The full API surface is documented via Swagger/OpenAPI (drf-spectacular), grouped into tags matching the app list below — that tag taxonomy is effectively the table of contents for integration. Besides the live Swagger UI, a versioned snapshot is committed at [`docs/openapi.yaml`](docs/openapi.yaml) so the contract can be browsed/diffed without running the server, or imported directly into Postman/Insomnia to auto-generate a request collection. Regenerate it after any endpoint change:
```bash
python manage.py spectacular --file docs/openapi.yaml
```

### Test accounts (for local integration — not real credentials)

Running `python manage.py seed_test_data` (dev only, refuses to run when `DEBUG=False`) creates three pre-verified accounts, all with password `TestPass123!`, plus realistic sample data across every app (an appointment history, health readings, an active diet plan, a medicine reminder with intake logs, notifications, exercise videos, an AI chat session, a resolved SOS event) so list/detail screens aren't empty on first integration:

| Email | Role | Notes |
|---|---|---|
| `patient@test.com` | patient | Sara Ahmed — profile complete, 12 weeks pregnant |
| `doctor@test.com` | doctor | Dr. Ayesha Malik — assigned to the test patient via their seeded appointments |
| `admin@test.com` | admin | Full system access |

Patients can't normally skip email verification, and doctor accounts can't normally self-register at all — this command exists specifically so a frontend developer isn't blocked by either of those in a local/dev environment. It's idempotent (safe to re-run) and creates no accounts or data outside `DEBUG=True`.

## Running tests

```bash
DJANGO_SETTINGS_MODULE=config.settings.test pytest
```
130+ tests across every app, with role-boundary coverage (patient/doctor/admin access matrices) treated as non-negotiable for every clinical endpoint — see `CLAUDE.md` for the conventions this project follows.

## Project layout

- `config/` — settings (`dev.py` / `prod.py` / `test.py`), root URLs, Celery app
- `apps/` — one Django app per bounded context:
  - `core` — shared base mixins, RBAC permission classes, pagination, exception handling
  - `accounts` — auth, roles, doctor provisioning
  - `appointments` — booking + the doctor↔patient assignment table every clinical app relies on
  - `health` — vitals, symptoms, water/kick trackers, pregnancy progress, baby-size reference
  - `diet` / `medicines` — doctor-authored diet plans, patient medicine reminders
  - `notifications` — in-app inbox, pluggable FCM/WhatsApp adapters, Celery Beat jobs
  - `hospitals` — Google Places nearby-hospital proxy (Redis-cached)
  - `ai_assistant` — AI pregnancy chat assistant (OpenAI/Gemini)
  - `emergency` — SOS with Celery-driven fan-out
  - `reports` — cross-app patient summary + admin system stats
- `render.yaml` — Render deployment topology (single free web service; Postgres is external, on Neon)
- `.github/workflows/scheduled-tasks.yml` — cron-triggered scheduled jobs, standing in for a paid Celery Beat worker
- `docs/openapi.yaml` — versioned API contract snapshot for frontend integration

See `.env.example` for every configuration variable, including third-party integrations (AI provider, WhatsApp Business API, Firebase Cloud Messaging, Google Places) which are all optional at boot — the app runs end-to-end without them via null/no-op adapters, and real credentials can be dropped in later with zero code changes.

See `CLAUDE.md` for the full architectural rationale, locked-in decisions, and per-phase build notes — it's written to let a fresh session (human or AI) pick this project up with full context. See `DEPLOYMENT.md` for step-by-step deployment instructions (Neon + Render + GitHub Actions, $0/month).
