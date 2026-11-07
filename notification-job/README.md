# notification-job

A Python script, run every hour, that finds who to remind in configuration-service's PostgreSQL database (with **SQLAlchemy 2.0**, psycopg 3). It **sends the payment reminders and the appointment reminders** (on WhatsApp and by email); the reconnect alerts are still only logged (sending them is a TODO).

Each run takes **the hour**: the time rounded down (9:11:30 pm → 9 pm). Then:

1. **Payment reminders:** orders and bookings still **pending payment** that were made **1 to 2 hours before the hour** (at least 1 hour old, under 2). **These are sent**, with the payment link (see below).
2. **Appointment reminders:** bookings starting **23 to 24 hours after the hour** (about a day ahead), unless their payment failed (they hold no time). A booking still pending payment is also asked to pay.
3. **WhatsApp reconnect alerts:** a business's WhatsApp connection (Embedded Signup) whose access token expires **in 7 days**, **in 1 day**, or **has just expired** (each alert at the first run after that point), while Meta still reports it connected. The alert goes to the business's active users with an email address, asking them to reconnect with Facebook on the Home page; reconnecting gives a new token and expiry. Like the reminders, it's only logged for now (sending it, e.g. by email, is a TODO).

Consecutive hourly runs' windows follow each other without gaps or overlaps, so each order / booking gets each reminder once. A reminder goes to the phone number of the chat the order / booking was placed in (none for a sandbox chat without one, or a deleted chat) and to its `email` detail.

A payment reminder on WhatsApp reads:

```
Hi Alice, this is Snap Studio. Your order #12 (2 × Kopi C, SGD 3.60) is still waiting for payment. Please complete it here: https://checkout.xendit.co/…

Reply here if you need any help.
```

## Sending the reminders

A reminder (an unpaid order / booking, or a booking starting in about 24 hours) goes out on both channels, each when the customer can be reached on it:

- **WhatsApp**, to the phone number of the chat the booking was made in. It goes through configuration-service's internal send endpoint (`app/whatsapp_sender.py`), which holds the business's WhatsApp token.
- **Email**, to the order's / booking's `email` detail (collected in the chat).

The emails end with how to reach the business: "just message Snap Studio on WhatsApp at +65 9123 4567", using the number of the business's WhatsApp connection (`display_phone_number`, as Meta shows it). A business with no number on record gets "just message Snap Studio in your WhatsApp chat" instead. The WhatsApp messages say "Reply here", since the customer is already in that chat.

What happens when a send fails:
- **A refusal** (a bad address) is logged, and the run still succeeds. Retrying wouldn't help.
- **A failure that could work later** (configuration-service or the mail relay can't be reached): the other reminders and the other channel still go out, then the run **exits 1**, so Cloud Run retries it. That may send the reminders that already went out a second time (better twice than never).

## The payment reminders and the payment link

A payment reminder carries the Xendit **payment link** (`payment_link` on the order / booking), the same link the customer got in the chat and on their invoice. Without a link (payment-ingester couldn't create one) it offers help instead ("Reply here if you need any help completing it").

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
| `INVOICE_CURRENCY` | `SGD` | The currency shown on a payment reminder's amount (the same setting as processing-service's documents). |
| `CONFIGURATION_SERVICE_URL` | `http://localhost:8000/api` | Where WhatsApp messages are sent through (docker-compose: `http://configuration-service:8000/api`). |
| `INTERNAL_API_KEY` | `dev-internal-api-key` | Must equal configuration-service's. In production a Secret Manager secret. |
| `EMAIL_ENABLED` | off | `true` turns email on. Off, `send_email()` only logs what it would send. |
| `EMAIL_FROM` / `EMAIL_FROM_NAME` | unset / `Ansera` | The sender, which the provider must have verified. |
| `SMTP_HOST` / `SMTP_PORT` | `smtp-relay.brevo.com` / `587` | STARTTLS. Cloud Run blocks port 25. |
| `SMTP_USERNAME` / `SMTP_PASSWORD` | unset | The provider's SMTP login and key. In production the key goes in Secret Manager. |
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

`tests/test_job.py` covers the reminders and the reconnect alerts (the windows' edges, the statuses, the messages, a chat without a phone number, the users alerted) on in-memory SQLite, so it needs no PostgreSQL. `tests/test_schema.py` checks the models against a Django-migrated PostgreSQL when `SCHEMA_DATABASE_URL` is set (CI's `schema` job).

## Project structure

```
notification-job/
├── app/
│   ├── config.py   # settings (environment variables)
│   ├── db.py       # SQLAlchemy engine and sessions (lazy)
│   ├── whatsapp_sender.py  # configuration-service's internal send endpoint
│   ├── email_sender.py     # send_email() through an SMTP relay
│   ├── models.py   # read-only models of configuration-service's tables
│   └── job.py      # run(): the payment and appointment reminders, WhatsApp reconnect alerts
├── tests/          # test_job.py, test_whatsapp_sender.py, test_email_sender.py, test_schema.py
├── run.py          # entry point: run once, exit code
├── cron.sh         # Docker: runs run.py on CRON_SCHEDULE (supercronic)
└── Dockerfile      # default command: run once (e.g. a Cloud Run Job)
```

## Deployment

On Google Cloud it's a Cloud Run Job with the image's default command, triggered hourly by Cloud Scheduler (`notification-tick`, `0 * * * *` UTC; `infrastructure/notification.tf`), instead of `cron.sh`. To send the reminders there, the job needs the settings above: `EMAIL_ENABLED=true`, the `EMAIL_*` / `SMTP_*` values (`SMTP_PASSWORD` from Secret Manager), `CONFIGURATION_SERVICE_URL` and `INTERNAL_API_KEY` (from Secret Manager), and its service account must be allowed to read those secrets. Without them it still runs, but sends nothing useful (WhatsApp fails to reach configuration-service, and email stays off).
