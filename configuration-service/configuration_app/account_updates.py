"""Meta's account_update webhooks: what they mean for a business's WhatsApp connection.

They go to our Meta app's own webhook (MESSAGING_INGESTER_PUBLIC_URL/webhook, Embedded Signup), which
messaging-ingester checks and forwards here (InternalWhatsAppAccountUpdatesView), one AccountUpdate per
change. The connections are found by their WhatsApp Business account (waba_id), so only Embedded Signup
connections are affected. What changes the status (anything else is only logged):

- disconnected: PARTNER_APP_UNINSTALLED (the business removed our app; only for our app's ID),
  PARTNER_REMOVED (the account is no longer shared with us), ACCOUNT_DELETED, ACCOUNT_OFFBOARDED (the
  number was registered again or moved to another device);
- banned: DISABLED_UPDATE with ban state DISABLE.

Nothing sets it back automatically (the user asked to keep it simple): connecting again with Embedded
Signup does (embedded_signup.connect).

Meta can redeliver a webhook: applying one twice changes nothing more.
"""

import logging
from dataclasses import dataclass

from django.conf import settings
from django.utils import timezone

from .models import WhatsAppConfiguration, WhatsAppConnectionStatus

logger = logging.getLogger(__name__)

DISCONNECTING_EVENTS = ('PARTNER_APP_UNINSTALLED', 'PARTNER_REMOVED', 'ACCOUNT_DELETED', 'ACCOUNT_OFFBOARDED')
BAN_EVENT, BANNED_STATE = 'DISABLED_UPDATE', 'DISABLE'


@dataclass(frozen=True)
class AccountUpdate:
    waba_id: str  # the WhatsApp Business account it's about
    event: str  # e.g. "PARTNER_APP_UNINSTALLED"
    ban_state: str = ''  # DISABLED_UPDATE's ban_info.waba_ban_state: DISABLE / REINSTATE / SCHEDULE_FOR_DISABLE
    partner_app_id: str = ''  # PARTNER_APP_(UN)INSTALLED's waba_info.partner_app_id


def apply(update: AccountUpdate) -> int:
    """Updates the connections of `update.waba_id` as the event says. Returns how many changed."""
    connections = WhatsAppConfiguration.objects.filter(waba_id=update.waba_id).exclude(waba_id='')
    if update.event in DISCONNECTING_EVENTS:
        if update.event == 'PARTNER_APP_UNINSTALLED' and update.partner_app_id not in ('', settings.META_APP_ID):
            return _ignore(update, 'another app')
        status = WhatsAppConnectionStatus.DISCONNECTED
    elif update.event == BAN_EVENT and update.ban_state == BANNED_STATE:
        status = WhatsAppConnectionStatus.BANNED
    else:  # e.g. a scheduled ban, a reinstatement, violations, restrictions, verification or pricing updates
        return _ignore(update, 'no status change')
    # QuerySet.update(): auto_now doesn't run, so last_updated is set here.
    now = timezone.now()
    changed = connections.exclude(status=status).update(status=status, status_updated_time=now, last_updated=now)
    logger.info('account_update %s %s for WABA %s: %d connection(s) changed', update.event, update.ban_state,
                update.waba_id, changed)
    return changed


def _ignore(update: AccountUpdate, why: str) -> int:
    logger.info('account_update %s %s for WABA %s: %s', update.event, update.ban_state, update.waba_id, why)
    return 0
