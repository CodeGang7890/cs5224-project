#!/bin/sh
# Start-up for local development (Docker): a clean database with every sample fixture, then the
# container's command (the dev server by default). Everything in the database is wiped each time.
set -e

python manage.py migrate --noinput
python manage.py flush --noinput
python manage.py loaddata \
    sample_business_configurations sample_business_users sample_products sample_faqs \
    sample_chat_configurations sample_chat_sessions sample_order_items
# The local superuser (not in a fixture, see CLAUDE.md): superuser / 123.
DJANGO_SUPERUSER_PASSWORD=123 python manage.py createsuperuser --noinput \
    --username superuser --email superuser@example.com

exec "$@"
