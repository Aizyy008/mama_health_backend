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
3. **Third-party integrations** (AI provider, WhatsApp Business API, Firebase Cloud Messaging, Google Places): client will supply real credentials **later**. Every integration is a pluggable adapter selected via env var presence, with a safe null/no-op fallback — the system must run end-to-end today and accept real keys later with **zero code changes**. This pattern lives in `notifications/adapters/factory.py` (template for all others); `hospitals/services.py::get_nearby_hospitals` and `ai_assistant/providers/factory.py` both follow the same shape (raise a clear error — 503, never a crash — when unconfigured).
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
| `health` | Blood pressure, blood sugar, symptoms, water intake, kick counter, pregnancy progress (computed, not stored), baby-size-by-week static reference | ✅ built (Phase 3) |
| `diet` | Doctor-authored `DietPlan` (meals, foods to avoid, hydration target) | ✅ built (Phase 4) |
| `medicines` | `MedicineReminder` + `MedicineIntakeLog` | ✅ built (Phase 4) |
| `notifications` | In-app `Notification`, FCM/WhatsApp adapters, Celery reminder/broadcast tasks | ✅ built (Phase 5) |
| `hospitals` | Google Places proxy, Redis-cached | ✅ built (Phase 6) |
| `ai_assistant` | `ChatSession`/`ChatMessage`, OpenAI/Gemini adapter, en/ur | ✅ built (Phase 7) |
| `reports` | Cross-app aggregation: doctor patient-summary, admin stats/broadcast, doctor/patient list-with-filters | ⏳ not started (Phase 8) |
| `emergency` | `EmergencySOSEvent` + fan-out via `notifications` | ✅ built (Phase 6) |

No separate "admin" Django app — Admin is a permission tier (`IsAdmin`), not a domain. Admin-only endpoints live in the app they belong to.

### Key modeling patterns (apply these consistently in every future phase)

- **Doctor↔Patient access**: never re-derive from `Appointment` queries ad hoc. Booking an appointment auto-creates (`apps/appointments/services.py::book_appointment`, transactional) a `PatientDoctorAssignment(patient, doctor)` row (idempotent via `get_or_create`; first doctor booked is flagged `is_primary`). Every **single-owner** clinical app (health, diet, medicines — one `patient` FK, any assigned doctor may act) checks this table via `core.viewsets.PatientScopedQuerysetMixin`.
  - **Important exception — `Appointment` itself does NOT use `PatientScopedQuerysetMixin`.** An appointment has *two* parties (a specific patient AND a specific doctor). Scoping a doctor's appointment list by "any patient assigned to me" would leak a *different* doctor's appointments with a shared patient — this was caught and fixed during Phase 2 (see `apps/appointments/tests/test_appointments.py::TestRoleScoping::test_doctor_does_not_see_another_doctors_appointment_with_a_shared_patient`, a real regression test, not hypothetical). `AppointmentViewSet` instead filters `doctor=request.user` directly, and uses a bespoke `apps/appointments/permissions.py::IsAppointmentParticipantOrAdmin` object permission rather than `core.permissions.IsOwnerPatientOrAssignedDoctorOrAdmin`. **Any future model with more than one "owning" party needs the same bespoke treatment — don't reflexively apply the generic mixin.**
- **RBAC**: `apps/core/permissions.py` has `IsPatient`, `IsDoctor`, `IsAdmin`, `IsDoctorOrAdmin`, `IsOwnerPatientOrAssignedDoctorOrAdmin`. `apps/core/viewsets.py` has `PatientScopedQuerysetMixin` (auto-scopes `get_queryset()` by role for any model with a `patient` FK) and `PatientOwnedCreateMixin` (forces `patient=request.user` on create when the requester is a patient). **Every new clinical viewset should mix these in rather than reimplementing scoping.**
- **"Daily reset" data (water intake, kick counter)**: never destructive. Every entry gets a denormalized `log_date`; "today" is a query-time `filter(log_date=today)`. No cron job resets anything — this avoids an entire class of midnight/timezone bugs. Apply this same pattern in `health` (Phase 3).
- **Computed, not stored**: pregnancy progress is derived from `PatientProfile.lmp_date`/`edd_date` at read time — don't add a `PregnancyProgress` model.
- **Object-level permissions never run on `create()`** — DRF only calls `has_object_permission` for retrieve/update/destroy, where an object already exists. Any check that depends on *which* patient a doctor is writing a record for (e.g. "is this doctor assigned to this patient?") must live in the **serializer's `validate()`**, not the permission class, or a doctor can write clinical data for any patient globally. This is exactly what `core.serializers.PatientOwnedModelSerializer.validate()` does — reuse it for every new patient-owned write.
  - **Subtlety found in Phase 4**: that `validate()` must distinguish create vs. update. `patient_id` is only *required* when creating on a patient's behalf — on a partial update (e.g. a doctor PATCHing just `{"notes": ...}`), an omitted `patient_id` legitimately means "keep the existing patient", not a missing field. The doctor-assignment check still re-runs on every update though (against `self.instance.patient` if not resupplied), in case a payload tries to reassign the record to a different patient. Get this wrong and every doctor-side PATCH/PUT 400s incorrectly — there was no test coverage for doctor updates until Phase 4's diet plan tests caught it.
  - **Indirect-patient models need a different approach entirely**: `MedicineIntakeLog` only reaches its patient via `reminder.patient`, not a direct FK — `IsOwnerPatientOrAssignedDoctorOrAdmin` (which reads `obj.patient_id`) would wrongly reject even the rightful owner. For a read-only viewset, `get_queryset()` scoping (via `patient_field_name="reminder__patient"`) already fully protects both list and retrieve, so no object permission class is needed there at all — see `apps/medicines/views.py::MedicineIntakeLogViewSet`.
- **`apps/core/utils.py::resolve_patient_from_request(request)`** — shared helper for any endpoint where a patient sees their own thing but a doctor/admin must pass `?patient_id=` (with the doctor's assignment checked). Used by `PregnancyProgressView` and `DietPlanViewSet.active`; reuse it rather than re-deriving this pattern a fourth time.
- **Pluggable third-party adapters**: every optional integration follows the same shape — an abstract adapter class, one or more concrete implementations, a `NullXAdapter`/no-op fallback, and a `get_x_adapter()` factory function keyed off `settings.X_CREDENTIAL` presence. See the template comment in `notifications/adapters/` once Phase 5 lands; until then, follow the shape described in the Notifications section of this file.
- **Error responses**: every error envelope is `{"detail": <one clear, specific, actionable sentence>, "errors": <per-field breakdown or null>}`, enforced globally by `apps/core/exceptions.py::custom_exception_handler`. `detail` is never a generic placeholder like "Validation failed." — it synthesizes the first real message found (DRF/Django's built-in field messages are already specific, e.g. "This password is too short. It must contain at least 8 characters."). When writing a NEW custom validation message anywhere (serializers, services raising `ValueError` that a view turns into a 400), phrase it as a complete, actionable sentence a patient/doctor could read directly — not a terse fragment. Get the HTTP status code right: 400 validation, 401 unauthenticated, 403 forbidden (authenticated but not allowed), 404 not found/not visible to this role, 429 throttled.
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

## Health endpoints (built, Phase 3)

```
GET/POST      /api/v1/health/blood-pressure/{,{id}/}    full CRUD, patient-owned
GET/POST      /api/v1/health/blood-sugar/{,{id}/}       full CRUD, patient-owned
GET/POST      /api/v1/health/symptoms/{,{id}/}          POST upserts by (patient, log_date) — see SymptomLogSerializer.create()
GET/POST      /api/v1/health/water-intake/               append-only (no update/delete)
GET           /api/v1/health/water-intake/today/         patient-only; aggregated total + today's entries
GET/POST      /api/v1/health/kick-sessions/               start a session
POST          /api/v1/health/kick-sessions/{id}/tap/      +1 kick
POST          /api/v1/health/kick-sessions/{id}/end/      sets ended_at
GET           /api/v1/health/baby-size/ , /baby-size/{week}/   read-only static reference (seeded)
GET           /api/v1/health/pregnancy-progress/          patient: own; doctor/admin: ?patient_id=, assignment-checked
```
All patient-owned viewsets use `core.viewsets.PatientScopedQuerysetMixin` + `PatientOwnedCreateMixin` + `core.serializers.PatientOwnedModelSerializer` — this is the normal case (contrast with Appointment's bespoke handling above).

## Diet & Medicines endpoints (built, Phase 4)

```
GET/POST/PATCH  /api/v1/diet/plans/{,{id}/}     doctor/admin write, patient read-only (403 on patient write)
GET             /api/v1/diet/plans/active/       resolve_patient_from_request-based; 404 if no active plan
GET/POST/PATCH  /api/v1/medicines/reminders/{,{id}/}         patient-owned (standard pattern)
POST            /api/v1/medicines/reminders/{id}/log-intake/  {status: taken|skipped, scheduled_for?}
GET             /api/v1/medicines/intake-logs/{,{id}/}        read-only, scoped via reminder__patient
```
`DietPlan`: only one `is_active=True` plan per patient — creating a new one deactivates (never deletes) the previous, preserving history (`apps/diet/services.py`). Meals/foods-to-avoid are nested writable serializers, replaced wholesale on update (delete + bulk_create), not diffed.

## Notifications architecture (built, Phase 5)

`apps/notifications/services.py::notify(recipient, notification_type, title, body, data, channels=[...])` is the single call site every other app uses — always writes a `Notification` row first (source of truth for the inbox), then best-effort dispatches push/WhatsApp via `apps/notifications/adapters/factory.py::get_push_adapter()` / `get_whatsapp_adapter()` (env-presence-keyed, `Null*Adapter` fallback, failures logged and never raise). **This factory pattern is the template every pluggable integration in this project follows** — `ai_assistant/providers/factory.py` (Phase 7) replicates it exactly.

```
GET  /api/v1/notifications/                     own inbox (scoped by recipient)
POST /api/v1/notifications/{id}/mark-read/
POST /api/v1/notifications/mark-all-read/
POST /api/v1/notifications/broadcast/            admin only; fans out via Celery (.delay()), returns 202 immediately
POST /api/v1/notifications/send-to-patient/      doctor only, assignment-checked; ad-hoc "doctor message"
```

**Celery Beat jobs** (`apps/notifications/tasks.py`, schedules seeded via a data migration — `apps/notifications/migrations/0002_seed_periodic_tasks.py`, using `django_celery_beat.PeriodicTask`/`IntervalSchedule`/`CrontabSchedule` so they're DB-editable without a deploy):
- `send_medicine_reminders` (every 5 min) — idempotent via a `MedicineIntakeLog` existence check for the exact `scheduled_for` timestamp.
- `send_appointment_reminders` (every 15 min, 60-min lookahead window) — idempotent via `Appointment.reminder_sent_at` (added in Phase 5 specifically for this).
- `send_weekly_pregnancy_update` (daily, 08:00 UTC) — only actually notifies patients whose `days_pregnant % 7 == 0`, so running once/day is naturally idempotent with no extra state.
- `cleanup_expired_invites_and_tokens` (daily, 02:00 UTC).
- `broadcast_notification` — NOT scheduled; triggered on-demand via `.delay()` from `BroadcastView`.

**Already wired into other apps** (not just built and left unused): `appointments/services.py::book_appointment` notifies the doctor (push+whatsapp); `transition_status` notifies whichever party didn't make the change (or both, if an admin made it); `diet/services.py::create_diet_plan`/`update_diet_plan` notify the patient; `emergency/tasks.py::fan_out_sos_alert` (Phase 6) notifies every assigned doctor + all admins. When future phases add new state-changing actions, wire a `notify()` call the same way rather than leaving it for later.

## Hospitals & Emergency endpoints (built, Phase 6)

```
GET  /api/v1/hospitals/nearby/?lat=..&lng=..&radius=5000   any authenticated user; 503 (not a crash) if unconfigured/upstream fails
GET/POST /api/v1/emergency/sos/{,{id}/}    create is patient-only (SOS can't be triggered "on behalf of" someone)
POST /api/v1/emergency/sos/{id}/resolve/   {status: resolved|false_alarm} — patient (self), assigned doctor, or admin
```
`EmergencySOSViewSet` is another bespoke-scoping case worth noting alongside Appointment: creation is patient-only via `get_permissions()` override (not the generic on-behalf-of pattern), because triggering someone else's SOS doesn't make sense. Reads use the normal `PatientScopedQuerysetMixin` though, since resolving is legitimately a doctor/admin action.

## AI Assistant endpoints (built, Phase 7)

```
GET/POST      /api/v1/ai/sessions/{,{id}/}       patient-only; one chat thread per session, language set at creation
GET/POST      /api/v1/ai/sessions/{id}/messages/  GET: full history. POST: {content} → persists user msg, calls provider, persists+returns assistant reply
```
`AI_PROVIDER` (`"openai"` | `"gemini"` | unset) + `AI_API_KEY` select the adapter via `apps/ai_assistant/providers/factory.py::get_ai_provider()`; unset → `NullAIProvider` raises a clean 503 rather than crashing, so the Flutter dev can build the chat UI against a stable contract before the client supplies real credentials. Language (`en`/`ur`) is passed to the provider as a system-prompt instruction (`providers/prompts.py::build_system_prompt`), not a separate translation step — both providers handle Urdu output fine when explicitly instructed. Throttled at the `ai_assistant` scope (20/hour, configured back in Phase 0) since LLM calls cost money — applied to the whole viewset via a class-level `throttle_scope` attribute (see gotcha below). Uses **`google-genai`**, not the deprecated `google-generativeai` package — if you see the latter imported anywhere, that's a regression, not a valid alternative.

**DRF `@action` gotcha hit in Phase 7**: two separately-named `@action`-decorated methods that happen to share the same `url_path` do **not** get merged into one route by the router — each becomes its own urlpattern with the identical path regex, and Django's resolver commits to the *first* one that matches the path, regardless of HTTP method, so the second one's method(s) 405 unreachably. To handle GET+POST at the same sub-resource URL (e.g. `sessions/{id}/messages/`), it must be **one** `@action(methods=["get", "post"], url_path="messages")` dispatching internally on `request.method` — see `ChatSessionViewSet.messages`. Same applies to any future sub-resource collection endpoint.

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
2. ✅ Appointments + `PatientDoctorAssignment` — booking, status state machine, doctor notes, doctor-scoped `PatientListView`; 13 passing tests
3. ✅ Health tracking — vitals, symptoms (upsert-by-day), water/kick trackers, computed pregnancy progress, seeded baby-size reference; 20 passing tests, plus a global fix: error responses now always carry a specific, actionable `detail` message — see "Error responses" convention above
4. ✅ Diet & Medicines — doctor-authored diet plans with one-active-per-patient history, medicine reminders + intake logging; 21 passing tests (75 total across the project). Also fixed a real bug found here: the shared `PatientOwnedModelSerializer.validate()` didn't distinguish create vs. update, so every doctor-side PATCH was wrongly 400ing — see the "Key modeling patterns" subtlety note above.
5. ✅ Notifications infra — in-app inbox, pluggable FCM/WhatsApp adapters (null fallbacks confirmed working end-to-end without real credentials), 4 seeded Celery Beat jobs, wired into appointments/diet as real triggers, not left dangling; 21 passing tests (96 total)
6. ✅ Hospitals proxy + Emergency SOS — Google Places Nearby Search proxy (Redis-cached by rounded lat/lng grid cell, 503 with a clear message on missing key or upstream failure, never a raw error), patient-initiated SOS with Celery-driven fan-out to assigned doctors + all admins + a direct WhatsApp message to the emergency contact (not a Notification row, since the contact isn't a system User); 18 passing tests (114 total)
7. ✅ AI Assistant — `ChatSession`/`ChatMessage`, OpenAI/Gemini adapters (`google-genai`, not the deprecated `google-generativeai`) with a `NullAIProvider` returning a clean 503 when unconfigured, patient-only access, 20/hour throttle scope already wired from Phase 0's settings; 8 passing tests (122 total)
8. ⏳ **Next**: Reports + admin aggregate views
9. Hardening pass (permission-matrix audit, rate-limit tuning, prod settings review, final Swagger pass)

**When resuming work**: check the status table above, `git log` for what's actually committed, and continue from the first ⏳ phase. Update this file's status table and roadmap section as each phase completes — it is the persistent memory for this project across machines/sessions.

## Things intentionally NOT done (don't add unless asked)

- No media/file upload storage (S3, Cloudinary, etc.) — see decision #5 above.
- No live video calling integration — see decision #2 above.
- No Docker container for the Django app itself in local dev — owner explicitly runs it via `manage.py runserver`.
- No test suite yet (Phase 1 gap, close it starting Phase 2 per the "Testing" section above).
