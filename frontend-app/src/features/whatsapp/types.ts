// Mirrors configuration-service configuration_app (WhatsAppConfigurationSerializer).

export type WhatsAppConnectionMethod = "manual" | "embedded_signup";

/**
 * What Meta last reported (account_update webhooks): `disconnected` (e.g. our app was removed in Meta,
 * or the account / number is gone) or `banned` (Meta disabled the account). Reconnecting resets it.
 */
export type WhatsAppConnectionStatus = "connected" | "disconnected" | "banned";

/**
 * What (if anything) the owner must do, computed by the backend: what Meta reported (`disconnected` /
 * `banned`) comes first, then the token's expiry: `expiring_soon` (reconnect before
 * `access_token_expires_time`) or `expired` (the assistant can't reply on WhatsApp until they reconnect).
 */
export type ConnectionHealth =
  "ok" | "expiring_soon" | "expired" | "disconnected" | "banned";

/** The business's WhatsApp connection. Secrets and webhook details are never returned. */
export interface WhatsAppConfiguration {
  phone_number_id: string;
  /** From Meta when the details were checked (read only), e.g. "+65 9123 4567". */
  display_phone_number: string;
  /** The business name Meta verified for the number (read only). */
  verified_name: string;
  /** The WhatsApp Business account, with Embedded Signup; empty when entered manually. */
  waba_id: string;
  /**
   * `embedded_signup`: connected with Facebook through our Meta app (the webhook is set up
   * automatically). `manual`: connected earlier with the owner's own Meta app (e.g. the sample data).
   */
  connection_method: WhatsAppConnectionMethod;
  status: WhatsAppConnectionStatus;
  /** Why it isn't connected, for the owner; empty while connected. */
  status_reason: string;
  /** When Meta reported the status; null if it never has. */
  status_updated_time: string | null;
  /** When Meta's access token expires (Embedded Signup tokens can, e.g. after 60 days); null: it doesn't. */
  access_token_expires_time: string | null;
  health: ConnectionHealth;
  created_time: string;
  last_updated: string;
}

/** POST /configuration/whatsapp/embedded-signup/: what Meta's Embedded Signup popup returned. */
export interface EmbeddedSignupInput {
  code: string;
  waba_id: string;
  phone_number_id: string;
}
