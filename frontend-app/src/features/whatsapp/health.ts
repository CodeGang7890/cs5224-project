import type { ConnectionHealth, WhatsAppConfiguration } from "./types";

/** E.g. "Wed 23 Dec 2026, 2:00 pm", in the browser's time zone. */
export function formatDateTime(time: string): string {
  return new Date(time).toLocaleString([], {
    weekday: "short",
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

/** The card's badge for each `health`. */
export const HEALTH_BADGES: Record<
  ConnectionHealth,
  { label: string; className: string }
> = {
  ok: {
    label: "Connected",
    className: "border-emerald-500/50 text-emerald-700 dark:text-emerald-400",
  },
  expiring_soon: {
    label: "Expires soon",
    className: "border-amber-500/50 text-amber-700 dark:text-amber-400",
  },
  expired: {
    label: "Expired",
    className: "border-destructive/50 text-destructive",
  },
  disconnected: {
    label: "Disconnected",
    className: "border-destructive/50 text-destructive",
  },
  banned: {
    label: "Banned",
    className: "border-destructive/50 text-destructive",
  },
};

/** The token expiry warning (`expiring_soon` / `expired`), or null otherwise (see the card's StatusAlert). */
export function reconnectMessage(config: WhatsAppConfiguration): string | null {
  const expires = config.access_token_expires_time;
  if (
    !expires ||
    (config.health !== "expiring_soon" && config.health !== "expired")
  )
    return null;
  return config.health === "expired"
    ? `Your WhatsApp connection expired on ${formatDateTime(expires)}, so your assistant can’t reply to customers on WhatsApp. Reconnect with Facebook to fix it.`
    : `Your WhatsApp connection expires on ${formatDateTime(expires)}. Reconnect with Facebook before then, or your assistant won’t be able to reply to customers on WhatsApp.`;
}
