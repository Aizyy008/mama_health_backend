# Mama Health — Backend (Claude Code context file)

This file exists so a Claude Code session on a **different machine** can pick up this project with full context. Read this before making changes.

## What this project is

Django REST API backend for **Mama Health**, a pregnancy-care platform. Three separate Flutter clients (Patient mobile, Doctor mobile, Admin Web) are being built by a separate frontend developer and consume this API exclusively — there is no server-rendered UI. My (the backend developer's) job is: the entire Django backend, role-based access control (Patient / Doctor / Admin), and Swagger/OpenAPI docs as the handoff contract to the Flutter developer. Source requirements were a client-provided `.docx` (not committed to this repo — see "Requirements" below for the extracted content).

**Owner's working style**: wants a clean, maintainable, production-ready backend, built and driven by Claude Code end-to-end ("access all the things on your own professionally"). Prefers Postgres/Redis run via Docker locally, but runs the Django app itself natively with `python manage.py runserver` — **do not** add the Django app itself to `docker-compose.yml`; only `db` and `redis` belong there.

## Requirements (from the client's original .docx, extracted 2026-07-29)

- **Auth**: Email registration, email verification, secure login, role-based access (Patient, Doctor, Admin).
- **Patient app**: Dashboard (Video Consultation, Appointments, Medicine Reminder, Reports, Health Tracker, Surgical Procedures, Diet Planner, AI Assistant); Health Tracker (baby size by week, water intake tracker w/ daily reset, kick counter w/ daily reset + history, today's symptoms by date, pregnancy progress %); Health Monitoring (blood pressure + blood sugar logging, history/graphs); Diet Planner (doctor-recommended meals, foods to avoid, hydration); AI Pregnancy Assistant (English & Urdu); Appointment Booking; Medicine Reminders; Nearby Hospitals via GPS; exercise/breathing videos; Emergency SOS; Reports & history; push notifications.
- **Doctor app**: Dashboard; patient management; appointment management; view patient reports; update diet plans; monitor BP/sugar/symptoms/kicks; appointment notifications via WhatsApp; patient consultation.
- **Admin dashboard** (Flutter Web, consumes the same API): system stats; manage doctors; manage patients; view all appointments; generate reports; broadcast notifications; monitor system.
- **Notifications**: medicine reminders, appointment reminders, diet updates, doctor messages, weekly pregnancy updates, emergency alerts.
- **Explicitly OUT of v1 scope** (client's "Future Enhancements"): live video calling, wearable integration, family access, lab report uploads, PDF reports, AI pregnancy risk prediction, prescription management, offline sync.

## Locked architecture decisions (confirmed with the project owner — do not re-litigate)

1. **Accounts**: Patients self-register + verify email. **Doctors are admin-provisioned only** (invite-link flow) — no public doctor signup. **Admin accounts are never created via HTTP** — only `python manage.py createsuperuser` or `python manage.py seed_admin` (reads `SEED_ADMIN_EMAIL`/`SEED_ADMIN_PASSWORD` from env).
2. **Video consultation**: `Appointment.appointment_type = "video_consultation"` + nullable `meeting_link` field only. No real video SDK (Agora/Twilio/Jitsi) integration in v1.
3. **Third-party integrations** (AI provider, WhatsApp Business API, Firebase Cloud Messaging, Google Places): client will supply real credentials **later**. Every integration is a pluggable adapter selected via env var presence, with a safe null/no-op fallback — the system must run end-to-end today and accept real keys later with **zero code changes**. This pattern lives in `notifications/adapters/factory.py` (template for all others) and is replicated in `ai_assistant/providers/factory.py` (Phase 7) and `hospitals/services.py` (Phase 6).
4. **Hospitals**: live proxy to Google Places Nearby Search (not an internally managed table), Redis-cached by rounded lat/lng grid cell to control API cost.
5. **No file/media uploads in v1** — all three Flutter clients use icon placeholders for profile pictures, not uploaded images. There is intentionally no S3/Cloudinary/media storage config — do not add one back without asking.
6. **Deployment target**: Render.com. Web service (gunicorn) + 2 background workers (Celery worker, Celery beat) + managed Postgres + managed Redis, defined in `render.yaml`. Local dev: Postgres + Redis run in Docker (`docker-compose.yml`), the Django app runs natively via `manage.py runserver` — **never containerize the Django app itself for local dev**, the owner explicitly doesn't want that.

## Tech stack

Django 5.1 + DRF 3.17, Python 3.13, PostgreSQL 14, Redis 7. `djangorestframework-simplejwt` (JWT, not Djoser — the custom admin-provisioned-doctor flow doesn't fit Djoser's opinions). `drf-spectacular` for OpenAPI/Swagger (not drf-yasg — unmaintained/OpenAPI2-only). `Celery` + `django-celery-beat` (DB-editable schedules) for background jobs. `django-environ` for `.env`-driven settings. `whitenoise` for static files. `django-redis` for cache. `pytest-django` + `factory_boy` for tests.

## App architecture

One Django app per bounded context, all under `apps/`:

| App | Responsibility | Status |
|---|---|---|
| `core` | Base model mixins, `Role` enum, permission classes, `PatientScopedQuerysetMixin`, pagination, exception handler, `/healthz/` | ✅ built |
| `accounts` | Custom `User` (email-based, `role` field), `PatientProfile`, `DoctorProfile`, `DoctorInvite`, email verification, JWT auth, doctor invite/provisioning | ✅ built (Phase 1) |
| `appointments` | `Appointment`, `PatientDoctorAssignment` (the derived doctor↔patient access table every other app checks) | ✅ built (Phase 2) |
| `health` | Blood pressure, blood sugar, symptoms, water intake, kick counter, pregnancy progress (computed, not stored), baby-size-by-week static reference | ⏳ not started (Phase 3) |
| `diet` | Doctor-authored `DietPlan` (meals, foods to avoid, hydration target) | ⏳ not started (Phase 4) |
| `medicines` | `MedicineReminder` + `MedicineIntakeLog` | ⏳ not started (Phase 4) |
| `notifications` | In-app `Notification`, FCM/WhatsApp adapters, Celery reminder/broadcast tasks | ⏳ not started (Phase 5) |
| `hospitals` | Google Places proxy, Redis-cached | ⏳ not started (Phase 6) |
| `ai_assistant` | `ChatSession`/`ChatMessage`, OpenAI/Gemini adapter, en/ur | ⏳ not started (Phase 7) |
| `reports` | Cross-app aggregation: doctor patient-summary, admin stats/broadcast, doctor/patient list-with-filters | ⏳ not started (Phase 8) |
| `emergency` | `EmergencySOSEvent` + fan-out via `notifications` | ⏳ not started (Phase 6) |

No separate "admin" Django app — Admin is a permission tier (`IsAdmin`), not a domain. Admin-only endpoints live in the app they belong to.

### Key modeling patterns (apply these consistently in every future phase)

- **Doctor↔Patient access**: never re-derive from `Appointment` queries ad hoc. Booking an appointment auto-creates (`apps/appointments/services.py::book_appointment`, transactional) a `PatientDoctorAssignment(patient, doctor)` row (idempotent via `get_or_create`; first doctor booked is flagged `is_primary`). Every **single-owner** clinical app (health, diet, medicines — one `patient` FK, any assigned doctor may act) checks this table via `core.viewsets.PatientScopedQuerysetMixin`.
  - **Important exception — `Appointment` itself does NOT use `PatientScopedQuerysetMixin`.** An appointment has *two* parties (a specific patient AND a specific doctor). Scoping a doctor's appointment list by "any patient assigned to me" would leak a *different* doctor's appointments with a shared patient — this was caught and fixed during Phase 2 (see `apps/appointments/tests/test_appointments.py::TestRoleScoping::test_doctor_does_not_see_another_doctors_appointment_with_a_shared_patient`, a real regression test, not hypothetical). `AppointmentViewSet` instead filters `doctor=request.user` directly, and uses a bespoke `apps/appointments/permissions.py::IsAppointmentParticipantOrAdmin` object permission rather than `core.permissions.IsOwnerPatientOrAssignedDoctorOrAdmin`. **Any future model with more than one "owning" party needs the same bespoke treatment — don't reflexively apply the generic mixin.**
- **RBAC**: `apps/core/permissions.py` has `IsPatient`, `IsDoctor`, `IsAdmin`, `IsDoctorOrAdmin`, `IsOwnerPatientOrAssignedDoctorOrAdmin`. `apps/core/viewsets.py` has `PatientScopedQuerysetMixin` (auto-scopes `get_queryset()` by role for any model with a `patient` FK) and `PatientOwnedCreateMixin` (forces `patient=request.user` on create when the requester is a patient). **Every new clinical viewset should mix these in rather than reimplementing scoping.**
- **"Daily reset" data (water intake, kick counter)**: never destructive. Every entry gets a denormalized `log_date`; "today" is a query-time `filter(log_date=today)`. No cron job resets anything — this avoids an entire class of midnight/timezone bugs. Apply this same pattern in `health` (Phase 3).
- **Computed, not stored**: pregnancy progress is derived from `PatientProfile.lmp_date`/`edd_date` at read time — don't add a `PregnancyProgress` model.
- **Pluggable third-party adapters**: every optional integration follows the same shape — an abstract adapter class, one or more concrete implementations, a `NullXAdapter`/no-op fallback, and a `get_x_adapter()` factory function keyed off `settings.X_CREDENTIAL` presence. See the template comment in `notifications/adapters/` once Phase 5 lands; until then, follow the shape described in the Notifications section of this file.
- **Swagger tags**: every view/viewset gets `@extend_schema(tags=["..."])` (or `@extend_schema_view(...)` for ViewSets) matching the `SPECTACULAR_SETTINGS["TAGS"]` list in `config/settings/base.py` — this tag taxonomy is the actual handoff table of contents for the Flutter developer.

## Auth endpoints (built, Phase 1)

```
POST /api/v1/auth/register/                    patient self-register
POST /api/v1/auth/verify-email/                 {token}
POST /api/v1/auth/resend-verification/          {email}
POST /api/v1/auth/login/                        JWT; blocks unverified patients; role embedded in claims
POST /api/v1/auth/token/refresh/
POST /api/v1/auth/logout/                       blacklists refresh token
POST /api/v1/auth/password/forgot/ , /reset/ , /change/
GET  /api/v1/auth/me/

POST  /api/v1/accounts/doctors/invite/          admin only
POST  /api/v1/accounts/doctors/invite/accept/   {token, password}
GET   /api/v1/accounts/doctors/                 any authenticated user (read); admin can PATCH
PATCH /api/v1/accounts/doctors/{id}/            admin only
GET   /api/v1/accounts/patients/                admin (all) / doctor (scoped to PatientDoctorAssignment)
GET/PATCH /api/v1/accounts/me/patient-profile/  patient only
GET/PATCH /api/v1/accounts/me/doctor-profile/   doctor only
```

Admin accounts: `createsuperuser` or `seed_admin` management command only.

## Appointments endpoints (built, Phase 2)

```
GET/POST  /api/v1/appointments/                       list (role-scoped) / book
GET/PATCH /api/v1/appointments/{id}/                   retrieve
POST      /api/v1/appointments/{id}/status/            {status, cancellation_reason?} — state-machine enforced
PATCH     /api/v1/appointments/{id}/doctor-notes/       doctor/admin only
```
Status state machine (`apps/appointments/services.py::ALLOWED_TRANSITIONS`): `pending → confirmed|cancelled`, `confirmed → completed|cancelled|no_show`; `completed`/`cancelled`/`no_show` are terminal. Booking: patients can only book for themselves (payload `patient_id` is ignored/overridden); doctor/admin booking on behalf of a patient must supply `patient_id` or get a 400.

## Notifications architecture (design target for Phase 5 — not yet built)

```python
def get_push_adapter():
    return FCMPushAdapter() if settings.FCM_CREDENTIALS_JSON else NullPushAdapter()
def get_whatsapp_adapter():
    return WhatsAppBusinessAPIAdapter() if settings.WHATSAPP_API_TOKEN else NullWhatsAppAdapter()
```
A `NotificationService.notify(recipient, type, title, body, data, channels=[...])` is the single call site every other app uses. It always writes a `Notification` row first, then best-effort dispatches push/WhatsApp (failures logged, never block the request). Celery Beat jobs: medicine reminders (~5 min), appointment reminders (~15–60 min), weekly pregnancy update (daily), invite/token cleanup (daily). Emergency SOS fan-out is on-demand via `.delay()`, not scheduled.

## Local dev setup

```bash
docker compose up -d          # Postgres (5432) + Redis (6380, mapped from container's 6379)
source venv/bin/activate      # venv/ already exists, gitignored
pip install -r requirements/dev.txt
python manage.py migrate
python manage.py runserver
```
`.env` already exists locally (gitignored, not committed) — copy `.env.example` if missing. Swagger UI: http://127.0.0.1:8000/api/docs/. `DJANGO_SETTINGS_MODULE` defaults to `config.settings.dev` via `manage.py`; production (`gunicorn`/Render) defaults to `config.settings.prod` via `wsgi.py`.

Note: Redis in `docker-compose.yml` is mapped to host port **6380** (not 6379) because another unrelated project's Redis container already occupies 6379 on this dev machine — that's a local-machine quirk, not a project requirement. On a fresh machine, port 6379 may be free; either port works as long as `.env`'s `REDIS_URL` matches the compose mapping.

## Testing

```bash
DJANGO_SETTINGS_MODULE=config.settings.test pytest
```
Non-negotiable priority (healthcare data): role-boundary/permission tests per clinical endpoint (patient A can't touch patient B's data; doctor access strictly gated by `PatientDoctorAssignment`; no endpoint can ever create an Admin). Write these **as each phase ships**, not deferred to the end.

Shared fixtures live in the **root** `conftest.py` (not inside an app) so they're visible to every app's tests: `patient_client` / `doctor_client` / `admin_client` / `anon_client` (pre-authenticated `APIClient` per role, JWT-based) and `patient_user` / `doctor_user` / `admin_user`. Per-app factories live in `apps/<app>/tests/factories.py` (e.g. `apps/accounts/tests/factories.py` has `PatientUserFactory`, `DoctorUserFactory`, `AdminUserFactory`). `apps/accounts/tests/test_auth.py` (21 tests, all passing) is the template to follow for every future phase's test file — registration/verification gating, JWT claim contents, invite-flow single-use tokens, and a full role-boundary matrix per endpoint.

## Build order / roadmap

0. ✅ Skeleton — settings split, `core` app, custom `User` model, drf-spectacular, `.env`/`.gitignore`, Render config, local Docker db/redis
1. ✅ Auth & Accounts — registration/verification/JWT/password-reset/doctor-invite, `/me`, 21 passing tests
2. ✅ Appointments + `PatientDoctorAssignment` — booking, status state machine, doctor notes, doctor-scoped `PatientListView`; 13 passing tests (34 total across the project)
3. ⏳ **Next**: Health tracking (BP, blood sugar, symptoms, water, kicks, pregnancy progress, baby-size reference) — apply `PatientScopedQuerysetMixin` + `PatientOwnedCreateMixin` from `core` here (this is the normal single-owner case, unlike Appointment)
4. Diet & Medicines
5. Notifications infra (Celery/Redis live, adapters with null fallbacks, in-app inbox)
6. Hospitals proxy + Emergency SOS
7. AI Assistant
8. Reports + admin aggregate views
9. Hardening pass (permission-matrix audit, rate-limit tuning, prod settings review, final Swagger pass)

**When resuming work**: check the status table above, `git log` for what's actually committed, and continue from the first ⏳ phase. Update this file's status table and roadmap section as each phase completes — it is the persistent memory for this project across machines/sessions.

## Things intentionally NOT done (don't add unless asked)

- No media/file upload storage (S3, Cloudinary, etc.) — see decision #5 above.
- No live video calling integration — see decision #2 above.
- No Docker container for the Django app itself in local dev — owner explicitly runs it via `manage.py runserver`.
- No test suite yet (Phase 1 gap, close it starting Phase 2 per the "Testing" section above).
