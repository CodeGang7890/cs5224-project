# CLAUDE.md: processing-service

Guidance for Claude Code when working in `processing-service/`. The README covers the endpoints, the Pub/Sub consumer, the payment flow and the settings.

## What this is

A FastAPI service, served by Gunicorn, on port **8003**. It pulls payment events (`{payment_reference, status, amount?}`) from Pub/Sub (`payment-events`). For each one, it checks the amount against the order's / booking's total, updates the order or booking with that payment reference (`app/payments.py`). It also sends two different documents, never mixed up (`app/documents.py`): an **invoice** when an order / booking is placed (a `created` event from payment-ingester: what to pay, and the payment link) and a **receipt** after the payment is received. After the commit it makes the PDF, uploads it to Cloud Storage (`app/storage.py`) and tells the customer (`app/notifications.py`): on WhatsApp through configuration-service's internal send endpoint (`app/whatsapp_sender.py`), and by email with the invoice PDF attached (`app/email_sender.py`, off unless `EMAIL_ENABLED`).

## The database (the user's rule)

- **configuration-service (Django) owns the PostgreSQL schema, and every migration is done there.** This service only queries rows and updates the ones its flow needs (order / booking status, a booking's weekly availability letters). Never create, alter or drop tables; no Alembic; no `create_all()` against PostgreSQL (the tests use it on SQLite only).
- `app/models.py` maps only the columns used. After a Django migration changes those tables, update the mapping. `tests/test_schema.py` (CI's `schema` job, on a Django-migrated PostgreSQL) checks they match.
- Django's signals don't run here, so `app/schedule.py` repaints a booking's provider's week itself (H → X when paid, back to O when failed), as `checkout_app.schedule.sync_booking` does.

## Commands (from `processing-service/`)

```bash
python -m unittest -v                              # must pass before finishing a change
gunicorn -c gunicorn.conf.py "app:create_app()"    # as in Docker
```
