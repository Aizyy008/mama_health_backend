# Deployment Guide — Mama Health Backend

Complete, step-by-step instructions to deploy this backend from scratch at **$0/month, no credit card required anywhere**. This is the practical companion to `CLAUDE.md`'s "Zero-cost deployment" section (which explains the *why* behind this architecture) — this file is the *how*, written so anyone (a new dev, or you on a fresh machine) can follow it top to bottom without prior context.

**Architecture at a glance**: Render free web service (Django + gunicorn) + Neon free Postgres (external, permanent free tier) + GitHub Actions free scheduled workflow (stands in for Celery Beat). No Redis, no dedicated worker process, no card on any platform.

---

## Prerequisites

- This repo pushed to a GitHub repository you control.
- A GitHub account (for the repo + Actions secrets).
- Nothing else — no card, no paid signup, anywhere.

---

## Step 1 — Create the database (Neon)

1. Go to [neon.tech](https://neon.tech) and sign up (no card required).
2. Create a new project (any name, e.g. `mama-health`).
3. Once created, open the project's **Connection Details** and copy the connection string. It looks like:
   ```
   postgres://<user>:<password>@<host>.neon.tech/<dbname>?sslmode=require
   ```
4. Keep this string handy — it's your `DATABASE_URL` for Step 2. Neon's free tier does not expire (unlike Render's own free Postgres, which is a time-limited trial — that's why Neon is used instead).

---

## Step 2 — Create the web service (Render)

1. Go to [render.com](https://render.com) and sign in / sign up.
2. **New → Web Service** → connect this GitHub repo.
3. Configure:
   - **Environment**: `Python 3`
   - **Instance type**: `Free`
   - **Build command**:
     ```
     pip install -r requirements.txt && python manage.py collectstatic --noinput && python manage.py migrate && python manage.py seed_admin
     ```
   - **Start command**:
     ```
     gunicorn config.wsgi:application --bind 0.0.0.0:$PORT
     ```
     (Render injects a `$PORT` env var — the app must explicitly bind to it or the service never becomes reachable.)
4. Add the environment variables below (Render dashboard → your service → **Environment**). You can also apply `render.yaml` directly as a Blueprint, which pre-fills the build/start commands and generates `SECRET_KEY` for you — you'll still need to set the rest manually since they're secrets not committed to the repo.

### Required environment variables

| Variable | Value | Notes |
|---|---|---|
| `DJANGO_SETTINGS_MODULE` | `config.settings.prod` | Selects the production settings module |
| `SECRET_KEY` | *(generate)* | Render's "Generate" button, or any long random string |
| `DATABASE_URL` | *(from Step 1)* | The Neon connection string, including `?sslmode=require` |
| `ALLOWED_HOSTS` | *(leave unset for now)* | Fill in after Step 3 once Render assigns your domain |
| `SEED_ADMIN_EMAIL` | e.g. `admin@mamahealth.app` | First admin login — see "Admin accounts" below |
| `SEED_ADMIN_PASSWORD` | *(a strong password)* | Paired with the email above |
| `CRON_SECRET` | *(any long random string)* | Must exactly match the GitHub Actions secret in Step 4 |

### Optional environment variables

Everything below is safe to leave unset — the app runs end-to-end with null/no-op fallbacks and no crashes. Set them only once the client supplies real credentials; no code changes are needed when you do.

| Variable | Purpose |
|---|---|
| `CORS_ALLOWED_ORIGINS` | Comma-separated origins once the Flutter Web admin's URL is known |
| `FRONTEND_URL` | Base URL used inside verification/reset emails (deep link or landing page) |
| `EMAIL_BACKEND` / `EMAIL_HOST` / `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` / `EMAIL_PORT` / `EMAIL_USE_TLS` | Real SMTP once available — defaults to the console backend, which just logs emails |
| `AI_PROVIDER` (`openai` or `gemini`) / `AI_API_KEY` / `AI_MODEL_NAME` | AI Pregnancy Assistant — 503s cleanly until set |
| `WHATSAPP_API_TOKEN` / `WHATSAPP_PHONE_NUMBER_ID` | WhatsApp appointment notifications |
| `FCM_CREDENTIALS_JSON` | Push notifications (paste the full Firebase service-account JSON as one line) |
| `GOOGLE_PLACES_API_KEY` | Nearby Hospitals — 503s cleanly until set |
| `REDIS_URL` / `CELERY_TASK_ALWAYS_EAGER=False` | Only if a real paid Celery worker is ever added later — see "Upgrading later" below |

Do **not** set `SECURE_SSL_REDIRECT` / `SECURE_HSTS_SECONDS` — their production defaults (in `config/settings/prod.py`) are already correct for Render.

5. Click **Create Web Service**. The first deploy will run the build command (installs deps, collects static files, runs migrations, seeds the admin account) and start gunicorn.

---

## Step 3 — Fix `ALLOWED_HOSTS`

Render only assigns your `*.onrender.com` domain after the first deploy, so `ALLOWED_HOSTS` can't be set until now.

1. Once the first deploy finishes, copy the domain Render assigned (e.g. `mama-health-api.onrender.com`).
2. Add/edit the `ALLOWED_HOSTS` environment variable with that value.
3. This triggers an automatic redeploy. Without this step, every request 400s.

---

## Step 4 — Wire up the scheduled tasks (GitHub Actions)

This replaces Celery Beat. A free GitHub Actions workflow (`.github/workflows/scheduled-tasks.yml`, already committed) pings a secret-protected endpoint on this backend every few minutes/daily to run medicine reminders, appointment reminders, the weekly pregnancy update, and expired-token cleanup.

1. In your GitHub repo: **Settings → Secrets and variables → Actions → New repository secret**. Add two secrets:
   - `BACKEND_BASE_URL` — your Render domain from Step 3, e.g. `https://mama-health-api.onrender.com`
   - `CRON_SECRET` — must be **exactly** the same value you set for `CRON_SECRET` in Step 2
2. That's it — the workflow is already committed and will start firing on its schedule (every 5 min for reminders, daily for the weekly update and cleanup).
3. **Known caveat**: GitHub disables scheduled workflows automatically if the repo goes 60 days with no commits. If reminders mysteriously stop, check the **Actions** tab → the workflow → re-enable it if disabled.

---

## Step 5 — Verify the deployment

Replace `<domain>` with your Render domain throughout.

1. **Health check**:
   ```bash
   curl https://<domain>/healthz/
   # → {"status": "ok"}
   ```
2. **Swagger UI loads**: open `https://<domain>/api/docs/` in a browser — this is the artifact you hand to the Flutter developer.
3. **Admin account seeded correctly** — log in with the credentials from `SEED_ADMIN_EMAIL` / `SEED_ADMIN_PASSWORD`:
   ```bash
   curl -X POST https://<domain>/api/v1/auth/login/ \
     -H "Content-Type: application/json" \
     -d '{"email": "<SEED_ADMIN_EMAIL>", "password": "<SEED_ADMIN_PASSWORD>"}'
   # → 200 with access/refresh tokens
   ```
4. **Cron path works end-to-end** — in GitHub: **Actions tab → "Scheduled Tasks" → "Run workflow"** (manual `workflow_dispatch` trigger). All four steps should succeed (green checkmarks). This confirms `CRON_SECRET` matches on both sides before waiting for the real schedule.
5. *(Optional, dev-blocker relief for the Flutter team)* — the `seed_test_data` management command is **DEBUG-only by design** and will refuse to run against this production deploy (`DEBUG=False`). It's meant for local dev only; don't try to run it on Render.

If all five checks pass, the backend is live and ready for the Flutter team to integrate against `https://<domain>/api/v1/` using `docs/openapi.yaml` / the live Swagger UI as the contract.

---

## Admin accounts

Admin accounts are **never** created via an HTTP endpoint — this is a deliberate security decision (see `CLAUDE.md` locked decision #1). The only two ways to create one:

- **`seed_admin` management command** — runs automatically on every deploy (folded into the Render build command, since free Render instances have no shell/SSH access to run it interactively). Idempotent — safe to redeploy repeatedly, reads `SEED_ADMIN_EMAIL`/`SEED_ADMIN_PASSWORD` from env.
- **`createsuperuser`** — only usable if you have shell access (i.e. local dev, or a paid Render plan with shell access).

To rotate the admin password later, change `SEED_ADMIN_PASSWORD` in Render's env vars and trigger a manual redeploy (Render dashboard → **Manual Deploy**).

---

## Redeploying after code changes

Render redeploys automatically on every push to the connected branch (default `main`). No manual step needed. If you only changed an environment variable, Render redeploys automatically as soon as you save it.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Every request returns 400 Bad Request | `ALLOWED_HOSTS` doesn't include the Render domain | Step 3 |
| `/internal/tasks/...` returns 403 | `CRON_SECRET` mismatch or unset on one side | Confirm the Render env var and the GitHub Actions secret are byte-for-byte identical |
| First request after idle is slow | Render free tier spins down after inactivity (cold start) | Expected — not a bug. The first GitHub Actions cron ping after a quiet period will also be slow for the same reason |
| Reminders silently stopped firing | GitHub auto-disables scheduled workflows after 60 days of no repo commits | Actions tab → workflow → re-enable |
| Admin login fails after first deploy | Build command didn't run `seed_admin`, or `SEED_ADMIN_EMAIL`/`SEED_ADMIN_PASSWORD` unset | Check Render's build logs for the `seed_admin` step; confirm both env vars are set, then Manual Deploy |
| AI Assistant / Hospitals endpoints return 503 | Expected when `AI_API_KEY` / `GOOGLE_PLACES_API_KEY` are unset | Not a bug — these are pluggable adapters with a clean 503 fallback until the client supplies real credentials |
| Migration fails during build | Neon connection string missing `?sslmode=require`, or Neon project paused/deleted | Re-copy the connection string from the Neon dashboard |
| Render's "New Web Service" flow asks for a card | Render's anti-fraud check couldn't auto-verify the account — happens even though Render's stated policy is card-free for the free instance type | See "If Render asks for a card" below |

### If Render asks for a card

Render's free web service is genuinely $0/no-card by policy, but its sign-up fraud check is account-specific and can still prompt for one. Before assuming there's no card-free path:
1. Double-check **Free** is actually selected as the instance type, not **Starter** (paid) — it's easy to click past this on the creation form.
2. Try signing up via **GitHub OAuth** instead of email/password, or from a different browser session — the fraud check is sometimes triggered by session/network signals, not a blanket account rule.
3. If it still asks: as of this writing, **Koyeb is not a usable fallback** — Mistral AI acquired Koyeb in February 2026 and closed its free Starter tier to new signups, pivoting the platform to enterprise AI/GPU workloads. Don't re-attempt Koyeb without first checking whether that's changed. Fly.io and Railway both now require a card unconditionally (deprecated their true free tiers). Re-run a fresh search for "no credit card required web hosting Django [current year]" before committing to another platform — this space changes fast and any list (including this one) can go stale within months.
4. If truly no card-free platform works, the realistic fallback is a small paid VPS (~$5–10/month, e.g. Oracle Cloud, DigitalOcean, Hetzner) running **Coolify** (free, open-source, self-hosted PaaS — gives a Render-like git-push deploy experience). This is a real budget change from the client's stated $0 constraint, so raise it with them explicitly rather than deciding unilaterally.

---

## Upgrading later (if the client agrees to pay, or traffic grows)

The zero-cost architecture is a deliberate, documented tradeoff — not a permanent ceiling. To move to a "real" async setup with a dedicated Celery worker:

1. Add a managed Redis instance (Render paid add-on, or any Redis host).
2. Set `REDIS_URL` and `CELERY_TASK_ALWAYS_EAGER=False` on the web service.
3. Add a Render **Background Worker** service running `celery -A config worker -l info`.
4. Add a Render **Background Worker** service running `celery -A config beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler`.
5. The `django_celery_beat.PeriodicTask` schedule rows are already seeded (`apps/notifications/migrations/0002_seed_periodic_tasks.py`) and become live again automatically — no code changes needed.
6. Disable/delete `.github/workflows/scheduled-tasks.yml` (now redundant with real Celery Beat).

See `CLAUDE.md`'s "Zero-cost deployment" section for the full rationale behind why this path was deferred in the first place.

---

## Reference

- `render.yaml` — the committed deployment topology (single free web service)
- `.github/workflows/scheduled-tasks.yml` — the cron workflow standing in for Celery Beat
- `.env.example` — every configuration variable with inline documentation
- `docs/openapi.yaml` — versioned API contract snapshot for the Flutter team
- `CLAUDE.md` — full architectural rationale and locked decisions (read this for *why*, this file for *how*)
