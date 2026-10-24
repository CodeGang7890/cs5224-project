import type { ChatConfiguration, ReplyStyleKey } from "./types";

// The welcome message and reply style (ChatConfiguration). Limits mirrored from
// configuration-service `chat_app/constants.py`; the backend validates too.
export const SETTINGS_LIMITS = {
  welcomeMessageMaxLength: 1000,
  customStyleMaxLength: 500,
} as const;

/** The only placeholder a welcome message may use. */
export const BUSINESS_NAME_PLACEHOLDER = "{business_name}";

export interface ChatSettings {
  welcome_message: string;
  reply_style: ReplyStyleKey;
  custom_style: string;
}

export function settingsOf(configuration: ChatConfiguration): ChatSettings {
  return {
    welcome_message: configuration.welcome_message,
    reply_style: configuration.reply_style,
    custom_style: configuration.custom_style,
  };
}

/** Trimmed, as the backend saves them (so comparing tells whether anything changed). */
export function normalizeSettings(settings: ChatSettings): ChatSettings {
  return {
    welcome_message: settings.welcome_message.trim(),
    reply_style: settings.reply_style,
    custom_style: settings.custom_style.trim(),
  };
}

export function sameSettings(a: ChatSettings, b: ChatSettings): boolean {
  return (
    JSON.stringify(normalizeSettings(a)) ===
    JSON.stringify(normalizeSettings(b))
  );
}

/** Problems per field (empty object = valid), like the backend's checks. */
export function validateSettings(
  settings: ChatSettings,
): Partial<Record<keyof ChatSettings, string>> {
  const errors: Partial<Record<keyof ChatSettings, string>> = {};
  const welcome = settings.welcome_message.trim();
  if (welcome.length > SETTINGS_LIMITS.welcomeMessageMaxLength) {
    errors.welcome_message = `Must be at most ${SETTINGS_LIMITS.welcomeMessageMaxLength.toLocaleString()} characters.`;
  } else {
    const unknown = [
      ...new Set(welcome.match(/\{[^{}]*\}|[{}]/g) ?? []),
    ].filter((match) => match !== BUSINESS_NAME_PLACEHOLDER);
    if (unknown.length) {
      errors.welcome_message = `Unknown placeholder ${unknown.join(", ")}: the only one you can use is ${BUSINESS_NAME_PLACEHOLDER}.`;
    }
  }
  const custom = settings.custom_style.trim();
  if (settings.reply_style === "custom" && !custom)
    errors.custom_style = "Describe the style you want (or choose a preset).";
  else if (custom.length > SETTINGS_LIMITS.customStyleMaxLength) {
    errors.custom_style = `Must be at most ${SETTINGS_LIMITS.customStyleMaxLength} characters.`;
  }
  return errors;
}

/** The welcome message as the customer gets it (like the backend's `welcome_message_text`). */
export function welcomePreview(
  welcomeMessage: string,
  businessName: string,
): string {
  return welcomeMessage
    .replaceAll(BUSINESS_NAME_PLACEHOLDER, businessName)
    .trim();
}
