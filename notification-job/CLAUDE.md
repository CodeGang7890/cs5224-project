# CLAUDE.md: notification-job

Guidance for Claude Code when working in `notification-job/`.

## What this is

A scheduled Python script (not a server). It will (1) read from the database, (2) apply business logic, and (3) call an external API. Only (1) exists so far: `app/job.py` `run()` reads `BusinessConfiguration` rows and logs them. The user said not to focus on (2) and (3) yet.

## Decisions (the user chose these)

- **A proper ORM: SQLAlchemy 2.0** (typed `Mapped[...]` models, `select()`), with psycopg 3 like configuration-service.
- **The database is configuration-service's PostgreSQL.** Django owns the schema: `app/models.py` maps existing tables **read-only**. Never create, alter or migrate tables from here (the test's `create_all` on SQLite is the only exception). Table names are Django's `<app_label>_<model>`, e.g. `configuration_app_businessconfiguration`. Map only the columns you need, and keep them in sync with the Django models.
- **Hourly cron in docker-compose.** The `notification-job` service runs `./cron.sh` (supercronic, `CRON_SCHEDULE`, default `0 * * * *` UTC). The image's default `CMD` runs the job once, ready for a Cloud Run Job plus Cloud Scheduler later.
- **One test only for now** (the user asked): `tests/test_job.py` on in-memory SQLite, passing a `sessionmaker` to `job.run()`.

## Conventions

- Settings live in `app/config.py` (ALL-CAPS, from env). The `POSTGRES_*` names match configuration-service's. The defaults reach compose's PostgreSQL from the host (`localhost:5433`).
- `app/db.py` creates the engine lazily (`lru_cache`, `NullPool`), so importing needs no database.
- `run.py` sets up logging and exits non-zero on failure, so the cron logs show failed runs.

## Commands (from `notification-job/`)

```bash
python -m unittest -v   # must pass before finishing a change
python run.py           # needs compose's PostgreSQL on localhost:5433
```
