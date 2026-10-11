#!/bin/sh
# Runs the job on a schedule (docker-compose's notification-job service). CRON_SCHEDULE is a
# standard 5-field cron expression, in UTC; default: every hour, on the hour.
set -e
echo "${CRON_SCHEDULE:-0 * * * *} python /app/run.py" > /tmp/crontab
echo "notification-job: running python run.py on schedule '${CRON_SCHEDULE:-0 * * * *}' (UTC)"
exec supercronic /tmp/crontab
