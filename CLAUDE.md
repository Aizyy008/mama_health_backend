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
6. **Deployment target — revised to $0/month (client budget constraint, decided 2026-07-31)**: originally planned as Render web service + 2 background workers (Celery worker, Celery beat) + managed Postgres + managed Redis. That plan is **superseded** — the client does not want to pay anything and does not want to add a card anywhere. Current model: **Render free web service + Neon free Postgres, nothing else**, defined in `render.yaml`. No managed Redis, no separate worker/beat services. See the dedicated "Zero-cost deployment" section below for the full rationale, runbook, and what's traded off. Local dev is unchanged: Postgres + Redis run in Docker (`docker-compose.yml`), the Django app runs natively via `manage.py runserver` — **never containerize the Django app itself for local dev**, the owner explicitly doesn't want that.

## Tech stack

Django 5.1 + DRF 3.17, Python 3.13, PostgreSQL 14, Redis 7. `djangorestframework-simplejwt` (JWT, not Djoser — the custom admin-provisioned-doctor flow doesn't fit Djoser's opinions). `drf-spectacular` for OpenAPI/Swagger (not drf-yasg — unmaintained/OpenAPI2-only). `Celery` + `django-celery-beat` (DB-editable schedules) for background jobs. `django-environ` for `.env`-driven settings. `whitenoise` for static files. `django-redis` for cache. `pytest-django` + `factory_boy` for tests.

## App architecture

One Django app per bounded context, all under `apps/`:

| App | Responsibility | Status |
|---|---|---|
| `core` | Base model mixins, `Role` enum, permission classes, `PatientScopedQuerysetMixin`, pagination, exception handler, `/healthz/` | ✅ built |
| `accounts` | Custom `User` (email-based, `role` field), `PatientProfile`, `DoctorProfile`, `DoctorInvite`, email verification, JWT auth, doctor invite/provisioning | ✅ built (Phase 1) |
| `appointments` | `Appointment`, `PatientDoctorAssignment` (the derived doctor↔patient access table every other app checks) | ✅ built (Phase 2) |
| `health` | Blood pressure, blood sugar, symptoms, water intake, kick counter, pregnancy progress (computed, not stored), baby-size-by-week reference, surgical procedures, exercise/breathing videos reference | ✅ built (Phase 3 + post-hardening additions) |
| `diet` | Doctor-authored `DietPlan` (meals, foods to avoid, hydration target) | ✅ built (Phase 4) |
| `medicines` | `MedicineReminder` + `MedicineIntakeLog` | ✅ built (Phase 4) |
| `notifications` | In-app `Notification`, FCM/WhatsApp adapters, Celery reminder/broadcast tasks | ✅ built (Phase 5) |
| `hospitals` | Google Places proxy, Redis-cached | ✅ built (Phase 6) |
| `ai_assistant` | `ChatSession`/`ChatMessage`, OpenAI/Gemini adapter, en/ur | ✅ built (Phase 7) |
| `reports` | Cross-app aggregation: patient/doctor summary report, admin system stats | ✅ built (Phase 8) |
| `emergency` | `EmergencySOSEvent` + fan-out via `notifications` | ✅ built (Phase 6) |

No separate "admin" Django app — Admin is a permission tier (`IsAdmin`), not a domain. Admin-only endpoints live in the app they belong to.

### Key modeling patterns (apply these consistently in every future phase)

- **Doctor↔Patient access**: never re-derive from `Appointment` queries ad hoc. Booking an appointment auto-creates (`apps/appointments/services.py::book_appointment`, transactional) a `PatientDoctorAssignment(patient, doctor)` row (idempotent via `get_or_create`; first doctor booked is flagged `is_primary`). Every **single-owner** clinical app (health, diet, medicines — one `patient` FK, any assigned doctor may act) checks this table via `core.viewsets.PatientScopedQuerysetMixin`.
  - **Important exception — `Appointment` itself does NOT use `PatientScopedQuerysetMixin`.** An appointment has *two* parties (a specific patient AND a specific doctor). Scoping a doctor's appointment list by "any patient assigned to me" would leak a *different* doctor's appointments with a shared patient — this was caught and fixed during Phase 2 (see `apps/appointments/tests/test_appointments.py::TestRoleScoping::test_doctor_does_not_see_another_doctors_appointment_with_a_shared_patient`, a real regression test, not hypothetical). `AppointmentViewSet` instead filters `doctor=request.user` directly, and uses a bespoke `apps/appointments/permissions.py::IsAppointmentParticipantOrAdmin` object permission rather than `core.permissions.IsOwnerPatientOrAssignedDoctorOrAdmin`. **Any future model with more than one "owning" party needs the same bespoke treatment — don't reflexively apply the generic mixin.**
- **RBAC**: `apps/core/permissions.py` has `IsPatient`, `IsDoctor`, `IsAdmin`, `IsDoctorOrAdmin`, `IsOwnerPatientOrAssignedDoctorOrAdmin`. `apps/core/viewsets.py` has `PatientScopedQuerysetMixin` (auto-scopes `get_queryset()` by role for any model with a `patient` FK) and `PatientOwnedCreateMixin` (forces `patient=request.user` on create when the requester is a patient). **Every new clinical viewset should mix these in rather than reimplementing scoping.** Since Phase 12, an admin caller can additionally narrow any of these endpoints to one patient via `?patient_id=` (previously admin only ever got the unfiltered "everyone" queryset, with no way to see just one patient's records — needed for the Admin Web patient-detail screen, which shows one patient's full BP/sugar/water/kicks/symptoms history). This is implemented once in the shared mixin, so it applies automatically to every consuming viewset (health, diet, medicines, emergency) without per-app changes.
- **"Daily reset" data (water intake, kick counter)**: never destructive. Every entry gets a denormalized `log_date`; "today" is a query-time `filter(log_date=today)`. No cron job resets anything — this avoids an entire class of midnight/timezone bugs. Apply this same pattern in `health` (Phase 3).
- **Computed, not stored**: pregnancy progress is derived from `PatientProfile.lmp_date`/`edd_date` at read time — don't add a `PregnancyProgress` model.
- **Object-level permissions never run on `create()`** — DRF only calls `has_object_permission` for retrieve/update/destroy, where an object already exists. Any check that depends on *which* patient a doctor is writing a record for (e.g. "is this doctor assigned to this patient?") must live in the **serializer's `validate()`**, not the permission class, or a doctor can write clinical data for any patient globally. This is exactly what `core.serializers.PatientOwnedModelSerializer.validate()` does — reuse it for every new patient-owned write.
  - **Subtlety found in Phase 4**: that `validate()` must distinguish create vs. update. `patient_id` is only *required* when creating on a patient's behalf — on a partial update (e.g. a doctor PATCHing just `{"notes": ...}`), an omitted `patient_id` legitimately means "keep the existing patient", not a missing field. The doctor-assignment check still re-runs on every update though (against `self.instance.patient` if not resupplied), in case a payload tries to reassign the record to a different patient. Get this wrong and every doctor-side PATCH/PUT 400s incorrectly — there was no test coverage for doctor updates until Phase 4's diet plan tests caught it.
  - **Indirect-patient models need a different approach entirely**: `MedicineIntakeLog` only reaches its patient via `reminder.patient`, not a direct FK — `IsOwnerPatientOrAssignedDoctorOrAdmin` (which reads `obj.patient_id`) would wrongly reject even the rightful owner. For a read-only viewset, `get_queryset()` scoping (via `patient_field_name="reminder__patient"`) already fully protects both list and retrieve, so no object permission class is needed there at all — see `apps/medicines/views.py::MedicineIntakeLogViewSet`.
- **`apps/core/utils.py::resolve_patient_from_request(request)`** — shared helper for any endpoint where a patient sees their own thing but a doctor/admin must pass `?patient_id=` (with the doctor's assignment checked). Used by `PregnancyProgressView` and `DietPlanViewSet.active`; reuse it rather than re-deriving this pattern a fourth time.
- **Pluggable third-party adapters**: every optional integration follows the same shape — an abstract adapter class, one or more concrete implementations, a `NullXAdapter`/no-op fallback, and a `get_x_adapter()` factory function keyed off `settings.X_CREDENTIAL` presence. See the template comment in `notifications/adapters/` once Phase 5 lands; until then, follow the shape described in the Notifications section of this file.
- **Error responses**: every error envelope is `{"detail": <one clear, specific, actionable sentence>, "errors": <per-field breakdown or null>}`, enforced globally by `apps/core/exceptions.py::custom_exception_handler`. `detail` is never a generic placeholder like "Validation failed." — it synthesizes the first real message found (DRF/Django's built-in field messages are already specific, e.g. "This password is too short. It must contain at least 8 characters."). When writing a NEW custom validation message anywhere (serializers, services raising `ValueError` that a view turns into a 400), phrase it as a complete, actionable sentence a patient/doctor could read directly — not a terse fragment. Get the HTTP status code right: 400 validation, 401 unauthenticated, 403 forbidden (authenticated but not allowed), 404 not found/not visible to this role, 429 throttled.
- **`apps/core/apps.py::CoreConfig.ready()`**: registers `ENUM_NAME_OVERRIDES` for every model that shares a "status" field name with a distinct choice set (`Appointment`, `MedicineIntakeLog`, `DoctorInvite`, `EmergencySOSEvent`) so drf-spectacular gives each a clean, stable schema component name instead of an auto-generated one. This has to happen in `ready()`, not at settings-module import time — Django models aren't loadable yet when `settings.py` runs, but they are once `ready()` fires (all apps' models are registered before any app's `ready()` runs). **Any new model that reuses a "status" (or similar) field name needs an entry added here.**
- **Swagger tags**: every view/viewset gets `@extend_schema(tags=["..."])` (or `@extend_schema_view(...)` for ViewSets) matching the `SPECTACULAR_SETTINGS["TAGS"]` list in `config/settings/base.py` — this tag taxonomy is the actual handoff table of contents for the Flutter developer.
  - **Gotcha found in the Phase 9 audit**: `@extend_schema_view(...)` only tags the actions you explicitly list — it's easy to cover `list`/`retrieve`/`create` and forget `partial_update`/`update`/`destroy` if the viewset supports them. An untagged action silently falls back to an auto-inferred (often wrongly-cased) tag instead of erroring, so it won't show up as broken — you have to actually check. `AppointmentViewSet`'s PATCH action was missing this way for several phases before being caught. Verify with: list every `http_method_names`-enabled action per viewset and confirm each appears in its `@extend_schema_view` block, or run the schema-vs-declared-tags diff shown in the Testing section's spirit (compare `schema['tags']` names against every operation's `tags` list).
- **Request/response examples**: every operation carries `OpenApiExample`s (a realistic request body, plus one example per meaningfully distinct response status). This is the actual API reference the Flutter dev works from — not just field types.
  - **Critical gotcha, found when this was audited**: drf-spectacular does **not** infer non-200 status codes from what a view's code actually returns — a plain `GenericAPIView.post()` that does `Response(..., status=201)` still gets a single auto-generated `200` response entry unless you **explicitly** pass `responses={201: SomeSerializer, 400: DetailResponseSerializer, ...}` to `@extend_schema`. `OpenApiExample(status_codes=["201"])` for a code that doesn't exist in `responses=` is **silently dropped** — no error, no warning, it just never appears in the schema. (`ModelViewSet.create()` is the one exception — DRF's `CreateModelMixin` convention is auto-detected correctly as 201.) `apps/core/serializers.py::DetailResponseSerializer` (`{detail, errors}`) exists purely to give these non-200 codes a schema entry to attach to. **Any new custom `@action`/`GenericAPIView` method that returns more than one status code needs an explicit `responses={...}` dict, or its non-default-status examples will vanish without any signal that something's wrong** — always spot-check with a script that walks the generated schema's `paths[...][method]['responses']` keys against what the view code actually returns, not just `manage.py spectacular`'s clean exit (a missing example produces zero warnings).
  - PUT and DELETE are deliberately left without their own examples across the API (PUT mirrors the POST/PATCH body already shown; DELETE has no request/response body) — that's intentional, not a gap, and `AppointmentViewSet`'s bare PATCH is also deliberately example-free since its docstring steers callers to `/status/`/`/doctor-notes/` instead.

## Auth endpoints (built, Phase 1)

```
POST /api/v1/auth/register/                    patient self-register
POST /api/v1/auth/verify-email/                 {token}
POST /api/v1/auth/resend-verification/          {email}
POST /api/v1/auth/login/                        JWT; blocks unverified patients; role embedded in claims
POST /api/v1/auth/token/refresh/
POST /api/v1/auth/logout/                       blacklists refresh token
POST /api/v1/auth/password/forgot/              {email} — emails a 6-digit OTP (not a link)
POST /api/v1/auth/password/verify-otp/          {email, otp_code} → {detail, reset_token}
POST /api/v1/auth/password/reset/               {token, new_password} — token is the reset_token from verify-otp
POST /api/v1/auth/password/change/
GET/PATCH /api/v1/auth/me/                      PATCH: first_name/last_name/phone_number only, any role

POST  /api/v1/accounts/doctors/invite/          admin only
POST  /api/v1/accounts/doctors/invite/accept/   {token, password}
GET   /api/v1/accounts/doctors/                 any authenticated user (read); admin can PATCH
PATCH /api/v1/accounts/doctors/{id}/            admin only
GET   /api/v1/accounts/patients/                admin (all, optional ?doctor_id=) / doctor (scoped to PatientDoctorAssignment)
GET   /api/v1/accounts/patients/{id}/           same scoping as list — doctor gets 404 if not assigned
PATCH /api/v1/accounts/patients/{id}/           admin only (e.g. is_active: false to deactivate — no delete endpoint)
POST  /api/v1/accounts/patients/{id}/assign-doctor/  admin only, {doctor_id} — manually creates a PatientDoctorAssignment
GET/PATCH /api/v1/accounts/me/patient-profile/  patient only
GET/PATCH /api/v1/accounts/me/doctor-profile/   doctor only
```

Admin accounts: `createsuperuser` or `seed_admin` management command only.

**Password reset is a 3-step OTP flow** (added Phase 12, replacing the original email-link flow): `forgot/` emails a 6-digit code (`PasswordResetOTP`, expires after `PASSWORD_RESET_OTP_EXPIRY_MINUTES`, default 10 min; requesting a new one invalidates any previous unused code for that user) → `verify-otp/` checks the code and, on success, issues a `PasswordResetToken` (the same mechanism the old link flow used) so the frontend doesn't resubmit the code again → `reset/` consumes that token exactly as before. This was a deliberate, in-place replacement (not an additive parallel flow) since nothing was in production yet when the Admin Web frontend dev requested OTP specifically — `reset/`'s request/response shape is unchanged, only what feeds it changed.

## Appointments endpoints (built, Phase 2)

```
GET/POST  /api/v1/appointments/                       list (role-scoped; admin optional ?patient_id=/?doctor_id=) / book
GET/PATCH /api/v1/appointments/{id}/                   retrieve
POST      /api/v1/appointments/{id}/status/            {status, cancellation_reason?} — state-machine enforced
PATCH     /api/v1/appointments/{id}/doctor-notes/       doctor/admin only
PATCH     /api/v1/appointments/{id}/reschedule/         {scheduled_at, duration_minutes?} — status untouched, 400 if terminal
```
Status state machine (`apps/appointments/services.py::ALLOWED_TRANSITIONS`): `pending → confirmed|cancelled`, `confirmed → completed|cancelled|no_show`; `completed`/`cancelled`/`no_show` are terminal. Booking: patients can only book for themselves (payload `patient_id` is ignored/overridden); doctor/admin booking on behalf of a patient must supply `patient_id` or get a 400. Reschedule (added Phase 12) is deliberately separate from `/status/` — it changes `scheduled_at`/`duration_minutes` without touching the state machine, 400s on a terminal-status appointment, and notifies the other party the same way status changes do (`apps/appointments/services.py::reschedule_appointment`).

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
GET/POST      /api/v1/health/surgical-procedures/{,{id}/} full CRUD, patient-owned (added post-hardening — see note below)
GET           /api/v1/health/exercise-videos/{,{id}/}     read-only; admin-managed via Django admin only, no write API
```
All patient-owned viewsets use `core.viewsets.PatientScopedQuerysetMixin` + `PatientOwnedCreateMixin` + `core.serializers.PatientOwnedModelSerializer` — this is the normal case (contrast with Appointment's bespoke handling above).

**Two doc items were missed in the original 9-phase build** and added afterward once caught: "Surgical Procedures" (dashboard nav item, patient-self-logged, same pattern as BP/blood sugar) and "Pregnancy exercise & breathing videos" (admin-managed reference table of external video links — `ExerciseVideo`, same read-only pattern as `BabySizeReference`; no video files are hosted, matching the no-media-storage decision). Both had zero elaboration anywhere else in the requirements doc, unlike Health Tracker/Diet Planner which got their own detailed bullet lists — that's *why* they were missed, not an excuse, just context if something else turns out to be missing later: **re-read the doc's dashboard/feature-list bullets specifically for single-mention items with no further detail**, since those are the ones that don't get their own section and are easy to skip. `ExerciseVideo` starts with an empty table — no placeholder video URLs were seeded (unlike baby-size facts, fabricating "real" video links would be actively wrong); the admin populates real content via `/admin/`.

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
`.delay()` above runs **synchronously in-process** in production now (`CELERY_TASK_ALWAYS_EAGER=True` by default — see "Zero-cost deployment" above), so `broadcast/` still returns 202 but the actual fan-out has already happened by the time it does; there's no real async gap to worry about with the current no-worker deployment.

**Celery Beat jobs** (`apps/notifications/tasks.py`) — **⚠️ the `django_celery_beat.PeriodicTask` rows seeded below are currently inert in production**, since there's no Celery Beat process running to read them (see "Zero-cost deployment" above — `.github/workflows/scheduled-tasks.yml` + `apps/core/views.py::run_scheduled_task` do this job instead by calling these same task functions directly on a schedule). The seed migration and `PeriodicTask` rows are left in place, not deleted, because they're the correct source of truth again the moment a real paid worker is ever added — at that point, re-enable `django-celery-beat` scheduling and this section's original design (schedules seeded via a data migration — `apps/notifications/migrations/0002_seed_periodic_tasks.py`, using `django_celery_beat.PeriodicTask`/`IntervalSchedule`/`CrontabSchedule` so they're DB-editable without a deploy) applies again unchanged:
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

## Reports endpoints (built, Phase 8)

```
GET /api/v1/reports/patient-summary/   patient: own; doctor/admin: ?patient_id= via resolve_patient_from_request
GET /api/v1/reports/admin/stats/       admin only — dashboard: counts + trimester_distribution + recent_activities
GET /api/v1/reports/search/?q=         admin only — global search across doctors/patients/appointments
```
`reports` has **no models of its own** — it's a pure cross-app read aggregator (`apps/reports/services.py` queries `health`/`diet`/`appointments`/`medicines` directly), which is exactly why it was built last: every other app's shape had to be settled first. The doc's admin "Manage doctors" / "Manage patients" / "View all appointments" features are **not** duplicated here — they already exist as `accounts.DoctorViewSet`, `accounts.PatientViewSet`, and `appointments.AppointmentViewSet` (admin sees all rows on each via the existing role-scoping). PDF export ("Generate reports" beyond JSON) is explicitly out of v1 scope per the doc's Future Enhancements list — don't add a PDF library unless asked.

**Admin dashboard additions (Phase 12)**: `admin/stats/` grew three fields for the Admin Web dashboard — `today_appointments` (today only, vs. the pre-existing `appointments_this_month`), `trimester_distribution` (buckets every patient with an LMP date set by current trimester; `unknown` = patients with a profile but no LMP date yet), and `recent_activities` (a computed-on-read feed of the most recent patient registrations/appointment bookings/SOS triggers, newest first — **not a stored Activity model**, matching this project's existing "computed, not stored" philosophy used for pregnancy progress; see `apps/reports/services.py::build_recent_activities`). `search/` (`apps/reports/services.py::search`) is a simple case-insensitive `icontains` match across doctor/patient name-or-email and appointment patient/doctor/reason fields, capped at 10 results per category — no full-text search infra (no Elasticsearch/pg trigram), matching this project's otherwise-minimal infra footprint; upgrade only if search quality actually becomes a problem at real data volume.

## Zero-cost deployment (added 2026-07-31 — client wants $0/month, no card anywhere)

**Why this exists**: the original plan (locked decision #6, now superseded) was Render web service + Celery worker + Celery beat + managed Postgres + managed Redis. Mid-deployment, the client made clear they won't pay anything and won't add a card to any platform. Render's free web service tier is genuinely $0/no-card, but background worker services and managed Redis are not — and Render prompted for a card at one point during the owner's dashboard session. This section documents the resulting architecture change.

**Update, deployed 2026-08-01**: the backend is now **live in production on Render's free tier, with no card ever added** — the earlier card prompt turned out to be a one-off/account-specific fraud check, not a hard policy wall (see DEPLOYMENT.md's "If Render asks for a card" troubleshooting section for what worked: confirming the **Free** instance type was actually selected, not **Starter**). Verified end-to-end: `/healthz/` returns 200, `/api/docs/` loads, `seed_admin` ran successfully in the build step, admin login works, and the GitHub Actions cron workflow ran successfully. Koyeb was briefly investigated as a card-free fallback and ruled out immediately — Mistral AI acquired Koyeb in February 2026 and closed its free tier to new signups — see DEPLOYMENT.md for that dead end so it isn't re-investigated.

**Platforms evaluated and rejected**:
- **PythonAnywhere free tier** — genuinely $0/no-card, but its free tier blocks outbound network connections to everything except a small whitelist, which would block the connection to an external Postgres (Neon) at the database-driver level, not just third-party APIs. Dead end for this project regardless of card requirement.
- **Rewriting in Node.js for Vercel** — considered and explicitly rejected. Vercel is serverless and has the *exact same* "no persistent background worker on the free tier" limitation as Render; a Node equivalent (BullMQ) needs a worker process too. Switching languages doesn't remove the constraint, it just costs days-to-weeks of re-implementing everything (auth, RBAC, all 11 apps, 137 tests) to arrive at the same architecture shape.

**Current model**: Render free web service (no card) + **Neon** free-tier Postgres (external, no card, doesn't expire — unlike Render's own free Postgres, which is a time-limited trial) + **GitHub Actions** free scheduled workflow standing in for Celery Beat. No Redis, no separate worker, no managed database on Render.

**What changed in code to make this possible**:
- `config/settings/base.py`: `REDIS_URL` now defaults to empty string. When unset, `CACHES` falls back to Django's local-memory backend (instead of `django_redis`) and `CELERY_BROKER_URL` is set to a dummy `memory://` value that's never actually contacted. **`CELERY_TASK_ALWAYS_EAGER` now defaults to `True`** (was `False`, only overridden in dev/test) — this means `task.delay()` calls (SOS fan-out, admin broadcast) execute synchronously in-process immediately, no broker or worker involved at all. Set `REDIS_URL` and `CELERY_TASK_ALWAYS_EAGER=False` later if a real Celery worker is ever added (e.g. once the client agrees to pay, or traffic grows enough to need real async fan-out).
- `apps/core/views.py::run_scheduled_task` + `config/urls.py` (`POST /internal/tasks/<task_name>/`, task_name ∈ `medicine-reminders` / `appointment-reminders` / `weekly-pregnancy-update` / `cleanup-tokens`) — a shared-secret-protected endpoint (header `X-Cron-Secret`, checked against `settings.CRON_SECRET`, fails closed/403 if `CRON_SECRET` is unset) that calls the underlying `@shared_task`-decorated function **directly** (not via `.delay()`), which just runs it synchronously like any normal function call — no Celery machinery involved regardless of the eager setting. Deliberately outside `/api/v1/` and excluded from Swagger (`@extend_schema(exclude=True)`) since it's not part of the public API contract; deliberately has **no throttle classes** (`@throttle_classes([])`) since it's legitimately called every few minutes by automation and the default `AnonRateThrottle` (100/day) would otherwise block it by mid-morning — the shared secret is its actual access control.
- `.github/workflows/scheduled-tasks.yml` — a GitHub Actions workflow with `on.schedule` cron entries (`*/5 * * * *` for medicine+appointment reminders, `0 8 * * *` and `0 2 * * *` for the two daily jobs) that `curl`s the corresponding `/internal/tasks/...` endpoint. Distinguishes which schedule fired via the `github.event.schedule` context variable so the right subset of curls run on each tick, rather than running all four jobs every 5 minutes (which would matter for `weekly-pregnancy-update` specifically — it's only idempotent at daily granularity, calling it every 5 minutes would spam duplicate weekly-update notifications throughout match-day). Also supports `workflow_dispatch` for manual testing (runs everything once). Requires two **GitHub repo secrets** (Settings → Secrets and variables → Actions): `BACKEND_BASE_URL` and `CRON_SECRET` (the latter must match the `CRON_SECRET` env var set on Render).
- `render.yaml` — reduced to a single free `web` service. `buildCommand` now also runs `python manage.py seed_admin` on every deploy (idempotent, so safe) since **free Render instances have no shell/SSH access** — this is the only way to get a first admin login without a paid plan. `DATABASE_URL` is no longer wired via `fromDatabase` (that only works for Render-native databases) — it's set manually to the Neon connection string.

**Known tradeoffs, stated explicitly so they're not mistaken for bugs later**:
- GitHub Actions scheduled workflows can run late under platform load (GitHub's own documented behavior, not something this project controls), and are **automatically disabled if the repo goes 60 days with no commits** — if reminders mysteriously stop firing after a long quiet period, check whether the workflow got disabled and re-enable it (Actions tab → the workflow → "Enable workflow").
- SOS fan-out and admin broadcast now block the HTTP response until every notification adapter call finishes (typically the `Null*Adapter`s, which are fast) — a small latency increase versus true async, judged an acceptable tradeoff for $0 hosting.
- Render's free web service spins down after inactivity, so the first request after a quiet period will be slow (cold start) — including the very first GitHub Actions cron ping of the day.
- Hospitals search caching now uses local-memory cache — it resets on every cold start/restart (free-tier instances restart often), so the cache is less effective than it'd be with real Redis, but still functionally correct (just calls Google Places slightly more often).

**Deployment runbook** (summary — see `DEPLOYMENT.md` for the full step-by-step guide with env var tables, verification checklist, and troubleshooting):
1. Create a free Postgres project on [neon.tech](https://neon.tech) (no card required). Copy its connection string (`sslmode=require` included).
2. In Render: New → Web Service → connect this GitHub repo → Free instance type.
   - Build command: `pip install -r requirements.txt && python manage.py collectstatic --noinput && python manage.py migrate && python manage.py seed_admin`
   - Start command: `gunicorn config.wsgi:application --bind 0.0.0.0:$PORT` — the `--bind` is required, Render injects `$PORT` but gunicorn doesn't read it automatically
   - Env vars: `DJANGO_SETTINGS_MODULE=config.settings.prod`, `SECRET_KEY` (Render's Generate button), `DATABASE_URL` (the Neon string from step 1), `SEED_ADMIN_EMAIL`, `SEED_ADMIN_PASSWORD`, `CRON_SECRET` (any long random string — generate one, it just needs to match step 4). Leave `ALLOWED_HOSTS` unset until step 3.
3. After first deploy, Render assigns a `*.onrender.com` domain — add it as `ALLOWED_HOSTS` and redeploy (or it'll 400 on every request).
4. In the GitHub repo: Settings → Secrets and variables → Actions → add `BACKEND_BASE_URL` (the Render domain from step 3) and `CRON_SECRET` (must exactly match step 2's value).
5. Verify: `GET https://<domain>/healthz/` → `{"status":"ok"}`; `GET https://<domain>/api/docs/` → Swagger UI loads; log in as `SEED_ADMIN_EMAIL`/`SEED_ADMIN_PASSWORD` via `POST /api/v1/auth/login/` to confirm the admin account seeded correctly.
6. Optional: manually trigger the GitHub Actions workflow once (Actions tab → "Scheduled Tasks" → "Run workflow") to confirm the cron path works end-to-end before waiting for the real schedule.

## Local dev setup

```bash
docker compose up -d          # Postgres (5432) + Redis (6380, mapped from container's 6379)
source venv/bin/activate      # venv/ already exists, gitignored
pip install -r requirements/dev.txt
python manage.py migrate
python manage.py runserver
```
`.env` already exists locally (gitignored, not committed) — copy `.env.example` if missing. Swagger UI: http://127.0.0.1:8000/api/docs/. `DJANGO_SETTINGS_MODULE` defaults to `config.settings.dev` via `manage.py`; production (`gunicorn`/Render) defaults to `config.settings.prod` via `wsgi.py`. A versioned OpenAPI snapshot lives at `docs/openapi.yaml` (the Flutter handoff artifact) — regenerate it after any endpoint change with `python manage.py spectacular --file docs/openapi.yaml` and commit the diff.

Note: Redis in `docker-compose.yml` is mapped to host port **6380** (not 6379) because another unrelated project's Redis container already occupies 6379 on this dev machine — that's a local-machine quirk, not a project requirement. On a fresh machine, port 6379 may be free; either port works as long as `.env`'s `REDIS_URL` matches the compose mapping.

**`python manage.py seed_test_data`** (`apps/accounts/management/commands/seed_test_data.py`) — creates `patient@test.com` / `doctor@test.com` / `admin@test.com` (password `TestPass123!` for all, pre-verified) plus sample data across every app. Built specifically for the Flutter handoff: patients can't normally skip email verification and doctors can't normally self-register at all, so without this a frontend dev would be blocked immediately. Refuses to run unless `DEBUG=True` (checked at the top of `handle()`) — never wire this into a prod deploy step. Idempotent — every write is behind a `get_or_create`/`update_or_create`/`.exists()` guard, safe to re-run. **When adding a new app/model, add a seed helper here too** — an empty list/detail screen on first frontend integration is a bad first impression and defeats the point of this command.

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
8. ✅ Reports + admin aggregate views — pure cross-app aggregation, no new models: patient summary (pregnancy progress, latest vitals, active diet plan, upcoming appointments, 7-day symptoms/medicine adherence) reusing `resolve_patient_from_request`, plus admin system stats (counts only — PDF export is explicitly out of v1 scope per the doc); 8 passing tests (130 total)
9. ✅ Hardening pass — full API audited endpoint-by-endpoint against its permission classes (no gaps found beyond what earlier phases' tests already caught); added a baseline `UserRateThrottle`/`AnonRateThrottle` safety net (2000/day, 100/day) alongside the existing scoped throttles, since previously anything without an explicit `throttle_scope` had zero rate-limit protection; confirmed a clean install of `requirements.txt` boots the app in an isolated venv; confirmed `collectstatic` and the full app run correctly under `config.settings.prod`; fixed the last real (non-cosmetic) Swagger gap — `AppointmentViewSet`'s PATCH action was missing from its `@extend_schema_view`, so it fell back to an auto-inferred lowercase `appointments` tag instead of `Appointments`; resolved the cosmetic multi-model "status" enum-naming collision properly via `CoreConfig.ready()` (see below) instead of leaving it as a warning; added a committed `docs/openapi.yaml` snapshot for the Flutter handoff. Schema generation is now 100% clean — 0 warnings, 0 errors. 130 tests passing at this point.
10. ✅ Post-hardening doc re-check — a direct "did you cover everything in the doc" question caught two single-mention dashboard items the 9-phase build had missed: Surgical Procedures and pregnancy exercise/breathing videos (see "Health endpoints" section above for what was added and why they were missed). 7 more tests (137 total).
11. ✅ Full Swagger request/response documentation pass — every one of the API's 100 operations got a `summary`, `description`, a realistic request example, and a response example per meaningfully distinct status code, prompted by the owner explicitly asking for comprehensive request/content/response structure documentation for the Flutter handoff. Found and fixed a real, silent gap along the way: non-200 status codes need an explicit `responses={...}` dict or their examples vanish with no warning (see the "Request/response examples" gotcha above) — this affected roughly 15 endpoints' worth of 201/400/401/403/404/503 examples before the fix. `docs/openapi.yaml` regenerated; no behavior changed, only documentation.
12. ✅ Admin Web dashboard support — the Flutter Admin Web dev sent a concrete screen-by-screen endpoint spec after starting integration; audited it against the actual API and found real gaps beyond doc mismatches. Built in one pass: **OTP-based forgot-password** (3-step: `forgot/` emails a 6-digit code → `verify-otp/` checks it and issues a reset token → `reset/` unchanged, consuming that token — replaces the original email-link flow in place, see "Auth endpoints" above); **profile update** (`PATCH /auth/me/`, previously read-only for every role, not just admin); **full patient CRUD** (`PatientListView` → `PatientViewSet`: retrieve/deactivate/`?doctor_id=` filter, mirroring the existing `DoctorViewSet` pattern — no delete endpoint, same "deactivate preserves clinical history" reasoning as doctors); **manual doctor assignment** (`POST /accounts/patients/{id}/assign-doctor/`, admin-only, since previously a `PatientDoctorAssignment` could only ever be created by booking an appointment); **admin `?patient_id=` filtering added to `core.viewsets.PatientScopedQuerysetMixin` itself** (one shared-mixin change that fixed "view one patient's full health history" across health/diet/medicines/emergency simultaneously, rather than a per-app fix); **appointment reschedule** as a distinct action from `/status/` (`PATCH /appointments/{id}/reschedule/`, notifies the other party, 400s on a terminal-status appointment) plus admin `?patient_id=`/`?doctor_id=` filters on the appointment list; **SOS `?status=` filter**; **dashboard stat additions** (`today_appointments`, `trimester_distribution`, `recent_activities` — the last one computed-on-read, no new model, same philosophy as pregnancy progress); and a **global search endpoint** (`GET /reports/search/?q=`, simple `icontains` across doctors/patients/appointments, no full-text search infra). Two real bugs caught and fixed during this phase, both worth remembering for future `@action`-heavy viewsets: (1) a custom `get_permissions()` override on a viewset silently ignores any `@action(permission_classes=[...])` kwarg unless the override explicitly checks for that action name too — `PatientViewSet.assign_doctor` initially fell through to the wrong (too-permissive) branch this way; (2) `http_method_names` is a Django-view-level allowlist, not per-route — adding `"post"` to unlock a custom detail action also silently unlocks `ModelViewSet`'s inherited list-level `create()`, which had to be explicitly overridden to raise `MethodNotAllowed` (patients must never be creatable directly, only via `/auth/register/`) rather than trusting the missing method to stay blocked. Also disabled DRF throttling entirely in `config/settings/test.py` — the shared-cache-across-tests throttle bleed this phase's added test volume triggered was a latent fragility in the existing suite, not a regression, and nothing was actually testing throttle behavior. 176 tests passing (was 143); `docs/openapi.yaml` regenerated, 0 schema warnings.

**Project status: every v1-scope feature in the requirements doc is implemented, tested, and documented, plus the Admin Web-specific additions above.** Remaining work going forward is either (a) real third-party credentials arriving from the client — zero code changes needed, just set env vars — or (b) genuinely new feature requests as the Flutter Admin Web integration continues, not gaps in this plan. If picking this up fresh, it's still worth doing one more line-by-line pass against the original doc text (reproduced near the top of this file) before assuming nothing else was missed.

**When resuming work**: check the status table above, `git log` for what's actually committed, and continue from the first ⏳ phase. Update this file's status table and roadmap section as each phase completes — it is the persistent memory for this project across machines/sessions.

## Things intentionally NOT done (don't add unless asked)

- No media/file upload storage (S3, Cloudinary, etc.) — see decision #5 above.
- No live video calling integration — see decision #2 above.
- No Docker container for the Django app itself in local dev — owner explicitly runs it via `manage.py runserver`.
- No PDF report generation — explicitly out of v1 scope per the doc's Future Enhancements list (see Reports section above).
- No wearable integration, family access, AI risk prediction, prescription management, or offline sync — all explicitly deferred by the client's own "Future Enhancements" list, not oversights.
