# CLAUDE.md: notification-job

Guidance for Claude Code when working in `notification-job/`.

## What this is

A scheduled Python script (not a server), run hourly. `app/job.py` `run(session_factory, now)` (the user asked) takes `floor_to_hour(now)` (rounded **down**, in UTC: the schedule time zone's offset is whole hours) and:
1. **Payment reminders** (`payment_reminders`): OrderItems and ScheduleItems with `order_status` `pending_payment` and `created_time` in `(hour − 2 h, hour − 1 h]` (made [1 h, 2 h) before the hour).
2. **Appointment reminders** (`appointment_reminders`): ScheduleItems with `start_time` in `[hour + 23 h, hour + 24 h)`, except `payment_failed` (my choice: they hold no time; a pending one is also asked to pay).
3. **WhatsApp reconnect alerts** (`reconnect_alerts`, the user asked: Embedded Signup tokens can expire, e.g. after 60 days): WhatsAppConfigurations with `status` `connected` (a disconnected / banned one shows that in the app instead) whose `access_token_expires_time` minus 7 d / 1 d / 0 (`RECONNECT_ALERTS_BEFORE`; the 7 days match configuration-service's `ACCESS_TOKEN_EXPIRY_WARNING`, when the app starts warning: keep them in sync) is in `(hour − 1 h, hour]`. Each `Alert` (business, the business's active users' non-empty `email`s (`BusinessUser`), a draft message: expires on … / has expired, reconnect with Facebook on Home) is **logged as a WARNING with "TODO"** (sending it, e.g. by email, comes later). Reconnecting renews the expiry, so the old token gets no more alerts.

The windows of consecutive hourly runs tile, so each item is reminded once. Each `Reminder` (kind, item, phone number from `chat_session.phone_number` (a relationship; None for a sandbox chat without one or a deleted chat), a draft message) is only **logged with "TODO"**: sending it (WhatsApp, e.g. through an outbound messages queue) comes later. Messages use the customer's `name` detail (else the chat's display name), the business name and local times (`SCHEDULE_TIME_ZONE`).

## Decisions (the user chose these)

- **A proper ORM: SQLAlchemy 2.0** (typed `Mapped[...]` models, `select()`), with psycopg 3 like configuration-service.
- **The database is configuration-service's PostgreSQL, and all migrations are done there only** (the user's rule; see the repo-root `CLAUDE.md`). This job only queries it. Django owns the schema: `app/models.py` maps existing tables **read-only**. Never create, alter or migrate tables from here (the test's `create_all` on SQLite is the only exception). Table names are Django's `<app_label>_<model>`, e.g. `configuration_app_businessconfiguration`. Map only the columns you need, and keep them in sync with the Django models.
- **Hourly cron in docker-compose.** The `notification-job` service runs `./cron.sh` (supercronic, `CRON_SCHEDULE`, default `0 * * * *` UTC). The image's default `CMD` runs the job once, ready for a Cloud Run Job plus Cloud Scheduler later.
- **Tests:** `tests/test_job.py` (the reminders and alerts on in-memory SQLite, `job.run(sessions, now=…)`; the window edges matter) and `tests/test_schema.py` (the models against a Django-migrated PostgreSQL, CI's `schema` job).

## Conventions

- Settings live in `app/config.py` (ALL-CAPS, from env). The `POSTGRES_*` names match configuration-service's. The defaults reach compose's PostgreSQL from the host (`localhost:5433`).
- `app/db.py` creates the engine lazily (`lru_cache`, `NullPool`), so importing needs no database.
- `run.py` sets up logging and exits non-zero on failure, so the cron logs show failed runs.

## Commands (from `notification-job/`)

```bash
python -m unittest -v   # must pass before finishing a change
python run.py           # needs compose's PostgreSQL on localhost:5433
```
