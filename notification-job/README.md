# notification-job

A Python script, run on a schedule, that will:

1. read from the database,
2. apply some business logic,
3. call an external API.

So far it does only (1). It reads the businesses (`configuration_app_businessconfiguration`) from configuration-service's PostgreSQL database with **SQLAlchemy 2.0** (psycopg 3) and logs them.

## Stack

| | |
| --- | --- |
| Python 3.14 | `run.py` runs the job once and exits: 0 on success, 1 on failure (the error is logged). |
| SQLAlchemy 2.0 + psycopg 3 | `app/models.py` maps Django's tables read-only. configuration-service owns the schema and migrations. |
| supercronic | Cron for containers (Docker only). `cron.sh` runs `python run.py` on `CRON_SCHEDULE`. |

## Environment variables

| Variable | Default | |
| --- | --- | --- |
| `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` | `configuration_service` / `postgres` / `postgres` | The same names as configuration-service. |
| `POSTGRES_HOST` / `POSTGRES_PORT` | `localhost` / `5433` | docker-compose's PostgreSQL from the host. In Docker: `postgres` / `5432`. |
| `DATABASE_URL` | unset | A full SQLAlchemy URL. Overrides the values above. |
| `CRON_SCHEDULE` | `0 * * * *` | Docker only (`cron.sh`): a 5-field cron expression, in UTC. |
| `LOG_LEVEL` | `INFO` | |

## Running

### With Docker (recommended)

From the repository root, `docker compose up --build` starts the `notification-job` container. It runs the job every hour, on the hour (UTC).

```bash
docker compose logs -f notification-job              # the cron's and the job's output
docker compose exec notification-job python run.py   # run it once now
NOTIFICATION_JOB_SCHEDULE="* * * * *" docker compose up -d notification-job   # every minute, to try the cron
```

### Without Docker

With docker-compose's PostgreSQL running (`docker compose up -d postgres configuration-service`):

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python run.py
```

## Tests

```bash
python -m unittest -v
```

The test uses in-memory SQLite, so it needs no PostgreSQL.

## Project structure

```
notification-job/
├── app/
│   ├── config.py   # settings (environment variables)
│   ├── db.py       # SQLAlchemy engine and sessions (lazy)
│   ├── models.py   # read-only models of configuration-service's tables
│   └── job.py      # run(): the job itself
├── tests/test_job.py
├── run.py          # entry point: run once, exit code
├── cron.sh         # Docker: runs run.py on CRON_SCHEDULE (supercronic)
└── Dockerfile      # default command: run once (e.g. a Cloud Run Job)
```

## Deployment

Not set up yet. On Google Cloud, this would be a Cloud Run Job with the image's default command, triggered hourly by Cloud Scheduler, instead of `cron.sh`.
