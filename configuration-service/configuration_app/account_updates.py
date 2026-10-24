"""Meta's account_update webhooks: what they mean for a business's WhatsApp connection.

They go to our Meta app's own webhook (MESSAGING_INGESTER_PUBLIC_URL/webhook, Embedded Signup), which
messaging-ingester checks and forwards here (InternalWhatsAppAccountUpdatesView), one AccountUpdate per
change. The connections are found by their WhatsApp Business account (waba_id), so only Embedded Signup
connections are affected. What changes the status (anything else is only logged):

- disconnected: PARTNER_APP_UNINSTALLED (the business removed our app; only for our app's ID),
  PARTNER_REMOVED (the account is no longer shared with us), ACCOUNT_DELETED, ACCOUNT_OFFBOARDED (the
  number was registered again or moved to another device);
- banned: DISABLED_UPDATE with ban state DISABLE;
- connected again: DISABLED_UPDATE with REINSTATE (if banned), ACCOUNT_RECONNECTED (if offboarded).
  Connecting again with Embedded Signup also sets it back (embedded_signup.connect).

Meta can redeliver a webhook: applying one twice changes nothing more.
"""

import logging
from dataclasses import dataclass

from django.conf import settings
from django.utils import timezone

from .models import WhatsAppConfiguration, WhatsAppConnectionStatus

logger = logging.getLogger(__name__)

DISCONNECTING_EVENTS = ('PARTNER_APP_UNINSTALLED', 'PARTNER_REMOVED', 'ACCOUNT_DELETED', 'ACCOUNT_OFFBOARDED')
BAN_EVENT = 'DISABLED_UPDATE'
RECONNECTED_EVENT = 'ACCOUNT_RECONNECTED'
OFFBOARDED_EVENT = 'ACCOUNT_OFFBOARDED'
BANNED_STATE, REINSTATED_STATE = 'DISABLE', 'REINSTATE'


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
        changed = _set(connections.exclude(status=WhatsAppConnectionStatus.DISCONNECTED, status_event=update.event),
                       WhatsAppConnectionStatus.DISCONNECTED, update.event)
    elif update.event == BAN_EVENT and update.ban_state == BANNED_STATE:
        changed = _set(connections.exclude(status=WhatsAppConnectionStatus.BANNED), WhatsAppConnectionStatus.BANNED,
                       update.event)
    elif update.event == BAN_EVENT and update.ban_state == REINSTATED_STATE:
        changed = _set(connections.filter(status=WhatsAppConnectionStatus.BANNED), WhatsAppConnectionStatus.CONNECTED,
                       update.event)
    elif update.event == RECONNECTED_EVENT:
        offboarded = connections.filter(status=WhatsAppConnectionStatus.DISCONNECTED, status_event=OFFBOARDED_EVENT)
        changed = _set(offboarded, WhatsAppConnectionStatus.CONNECTED, update.event)
    else:  # e.g. a scheduled ban, violations, restrictions, verification or pricing updates
        return _ignore(update, 'no status change')
    logger.info('account_update %s %s for WABA %s: %d connection(s) changed', update.event, update.ban_state,
                update.waba_id, changed)
    return changed


def _set(connections, status: str, event: str) -> int:
    # QuerySet.update(): auto_now doesn't run, so last_updated is set here.
    now = timezone.now()
    return connections.update(status=status, status_event=event, status_updated_time=now, last_updated=now)


def _ignore(update: AccountUpdate, why: str) -> int:
    logger.info('account_update %s %s for WABA %s: %s', update.event, update.ban_state, update.waba_id, why)
    return 0
