import type { WhatsAppConfiguration } from './types'

/** E.g. "Wed 23 Dec 2026, 2:00 pm", in the browser's time zone. */
export function formatExpiry(time: string): string {
  return new Date(time).toLocaleString([], {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

/**
 * What to tell the owner about their token's expiry, or null while there's nothing to do. Only while
 * Meta reports the connection connected: otherwise its status (disconnected / banned) is shown instead.
 */
export function reconnectMessage(config: WhatsAppConfiguration): string | null {
  const expires = config.access_token_expires_time
  if (!expires || config.status !== 'connected' || config.access_token_status === 'active') return null
  return config.access_token_status === 'expired'
    ? `Your WhatsApp connection expired on ${formatExpiry(expires)}, so your assistant can’t reply to customers on WhatsApp. Reconnect with Facebook to fix it.`
    : `Your WhatsApp connection expires on ${formatExpiry(expires)}. Reconnect with Facebook before then, or your assistant won’t be able to reply to customers on WhatsApp.`
}
