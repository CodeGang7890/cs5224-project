"""Sends one real email, to check the SMTP settings (Brevo).
    
    python scripts/send_test_email.py name@example.com ["subject"] ["body"]
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def load_root_env() -> None:
    import os

    env_file = ROOT.parent / '.env'
    if not env_file.is_file():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            key, _, value = line.partition('=')
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_root_env()

from app import config, email_sender

if len(sys.argv) < 2 or '@' not in sys.argv[1]:
    sys.exit(__doc__)

recipient = sys.argv[1]
subject = sys.argv[2] if len(sys.argv) > 2 else 'Ansera test email'
body = sys.argv[3] if len(sys.argv) > 3 else 'This is only to see if SMTP works.'

print(f'Sending through {config.SMTP_HOST}:{config.SMTP_PORT} as {config.SMTP_USERNAME or "(no login)"}, '
      f'from {config.EMAIL_FROM_NAME} <{config.EMAIL_FROM}> to {recipient}')
try:
    email_sender.send_email(subject, body, recipient, force=True)
except email_sender.EmailError as exc:
    sys.exit(f'Not sent ({"could work later" if exc.retryable else "will not work as is"}): {exc}')
print('Sent. Check the inbox, and the spam folder.')
