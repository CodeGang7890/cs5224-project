#!/bin/sh
# Runs the job on a schedule (docker-compose's notification-job service). CRON_SCHEDULE is a
# standard 5-field cron expression, in UTC; default: every hour, on the hour.
set -e
echo "${CRON_SCHEDULE:-0 * * * *} python /app/run.py" > /tmp/crontab
echo "notification-job: running python run.py on schedule '${CRON_SCHEDULE:-0 * * * *}' (UTC)"
# Absolute path: as PID 1, supercronic re-runs itself (os.Args[0]) to reap zombies, which fails for a bare name.
exec /usr/local/bin/supercronic /tmp/crontab
