# notification-job

A Python script, run every hour, that finds who to remind in configuration-service's PostgreSQL database (with **SQLAlchemy 2.0**, psycopg 3) and, for now, logs the reminders. Sending them (WhatsApp) is a TODO.

Each run takes **the hour**: the time rounded down (9:11:30 pm → 9 pm). Then:

1. **Payment reminders:** orders and bookings still **pending payment** that were made **1 to 2 hours before the hour** (at least 1 hour old, under 2).
2. **Appointment reminders:** bookings starting **23 to 24 hours after the hour** (about a day ahead), unless their payment failed (they hold no time). A booking still pending payment is also asked to pay.

Consecutive hourly runs' windows follow each other without gaps or overlaps, so each order / booking gets each reminder once. For each, the job logs the customer's phone number (from the chat the order / booking was placed in; none for a sandbox chat without one, or a deleted chat) and a draft message:

```
TODO: send payment reminder for order #12 to +6591234567: Hi Alice, this is Snap Studio. Your order #12 (total $3.60) is still waiting for payment. Please complete it with payment reference 3f9c…, or reply here if you need any help.
```

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
| `SCHEDULE_TIME_ZONE` | `Asia/Singapore` | The time zone of the times in the messages (configuration-service's `DJANGO_SCHEDULE_TIME_ZONE`). |
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

`tests/test_job.py` covers both reminders (the windows' edges, the statuses, the messages, a chat without a phone number) on in-memory SQLite, so it needs no PostgreSQL. `tests/test_schema.py` checks the models against a Django-migrated PostgreSQL when `SCHEMA_DATABASE_URL` is set (CI's `schema` job).

## Project structure

```
notification-job/
├── app/
│   ├── config.py   # settings (environment variables)
│   ├── db.py       # SQLAlchemy engine and sessions (lazy)
│   ├── models.py   # read-only models of configuration-service's tables
│   └── job.py      # run(): the payment and appointment reminders
├── tests/          # test_job.py, test_schema.py
├── run.py          # entry point: run once, exit code
├── cron.sh         # Docker: runs run.py on CRON_SCHEDULE (supercronic)
└── Dockerfile      # default command: run once (e.g. a Cloud Run Job)
```

## Deployment

Not set up yet. On Google Cloud, this would be a Cloud Run Job with the image's default command, triggered hourly by Cloud Scheduler, instead of `cron.sh`.
