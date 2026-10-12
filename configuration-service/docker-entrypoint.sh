#!/bin/sh
# Start-up for local development (Docker): migrate, set up the data, then run the container's
# command (the dev server by default).
#
# RESET_DB=true wipes the database (flush) and loads every sample fixture. Otherwise the data is
# kept between runs, and the fixtures are only loaded the first time (when the database is empty).
set -e

load_sample_data() {
    python manage.py loaddata \
        sample_business_configurations sample_whatsapp_configurations sample_business_users sample_products sample_faqs sample_services \
        sample_chat_configurations sample_chat_sessions sample_order_items sample_schedule_items \
        sample_unanswered_questions
    # The local superuser (not in a fixture, see CLAUDE.md): superuser / 123.
    DJANGO_SUPERUSER_PASSWORD=123 python manage.py createsuperuser --noinput \
        --username superuser --email superuser@example.com
}

python manage.py migrate --noinput

case "$(echo "${RESET_DB:-false}" | tr '[:upper:]' '[:lower:]')" in
    true | 1 | yes)
        echo "RESET_DB is on: resetting the database to the sample data."
        python manage.py flush --noinput
        load_sample_data
        ;;
    *)
        if python manage.py shell -c "from configuration_app.models import BusinessConfiguration as B; raise SystemExit(0 if B.objects.exists() else 1)"; then
            echo "Keeping the existing data (set RESET_DB=true to reset it)."
        else
            echo "Empty database: loading the sample data."
            load_sample_data
        fi
        ;;
esac

exec "$@"
