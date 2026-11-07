"""Entry point: `python run.py` runs the job once and exits (non-zero on failure).

In docker-compose, cron.sh runs it every hour.
"""

import logging
import sys

from app import config, job

if __name__ == '__main__':
    logging.basicConfig(level=config.LOG_LEVEL, format='%(asctime)s %(levelname)s %(name)s: %(message)s')
    try:
        result = job.run()
        if result.failed_reminders:
            logging.getLogger('notification-job').error('%d reminders failed', len(result.failed_reminders))
            sys.exit(1)
    except Exception:
        logging.getLogger('notification-job').exception('Notification job failed')
        sys.exit(1)
