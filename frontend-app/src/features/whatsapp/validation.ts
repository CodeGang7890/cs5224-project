import type { WhatsAppConfiguration, WhatsAppConfigurationInput } from './types'

// Mirrors configuration-service configuration_app/models.py. The backend validates too; this just
// gives instant feedback.
export const WHATSAPP_LIMITS = {
  phoneNumberIdMaxLength: 32,
  accessTokenMaxLength: 1000,
  appSecretMaxLength: 128,
} as const

export interface WhatsAppFormValues {
  phone_number_id: string
  access_token: string
  app_secret: string
}

export type WhatsAppFormErrors = Partial<Record<keyof WhatsAppFormValues, string>>

export type SecretField = 'access_token' | 'app_secret'

export const SECRET_LABELS: Record<SecretField, string> = { access_token: 'access token', app_secret: 'App Secret' }

export function whatsAppToFormValues(config: WhatsAppConfiguration | null): WhatsAppFormValues {
  // The secrets are never sent back: the form only holds a secret the owner is entering.
  return { phone_number_id: config?.phone_number_id ?? '', access_token: '', app_secret: '' }
}

/** The PUT body: a secret is only sent when a new one was entered; otherwise the saved one is kept. */
export function formValuesToWhatsAppInput(values: WhatsAppFormValues): WhatsAppConfigurationInput {
  const input: WhatsAppConfigurationInput = { phone_number_id: values.phone_number_id.trim() }
  const accessToken = values.access_token.trim()
  const appSecret = values.app_secret.trim()
  if (accessToken) input.access_token = accessToken
  if (appSecret) input.app_secret = appSecret
  return input
}

/** Labels of what the form would change, for the confirmation message. */
export function changedWhatsAppFields(saved: WhatsAppConfiguration | null, input: WhatsAppConfigurationInput): string[] {
  const changed: string[] = []
  if (input.phone_number_id !== (saved?.phone_number_id ?? '')) changed.push('Phone Number ID')
  if (input.access_token) changed.push('access token')
  if (input.app_secret) changed.push('App Secret')
  return changed
}

const DIGITS = /^\d+$/
const WHITESPACE = /\s/

function validateSecret(value: string, maxLength: number, required: string | undefined): string | undefined {
  const trimmed = value.trim()
  if (!trimmed) return required
  if (WHITESPACE.test(trimmed)) return 'Must not contain spaces.'
  if (trimmed.length > maxLength) return `Must be at most ${maxLength.toLocaleString()} characters.`
  return undefined
}

/**
 * Returns an error message per invalid field (empty object = valid). Secrets are required when
 * connecting, and when the owner chose to replace a saved one (`replacing`).
 */
export function validateWhatsApp(
  values: WhatsAppFormValues,
  isConnected: boolean,
  replacing: Record<SecretField, boolean> = { access_token: false, app_secret: false },
): WhatsAppFormErrors {
  const errors: WhatsAppFormErrors = {}
  const phoneNumberId = values.phone_number_id.trim()
  if (!phoneNumberId) errors.phone_number_id = 'Phone Number ID is required.'
  else if (!DIGITS.test(phoneNumberId)) errors.phone_number_id = 'Must contain digits only.'
  else if (phoneNumberId.length > WHATSAPP_LIMITS.phoneNumberIdMaxLength) {
    errors.phone_number_id = `Must be at most ${WHATSAPP_LIMITS.phoneNumberIdMaxLength} digits.`
  }
  const requiredMessage = (field: SecretField) =>
    !isConnected
      ? 'Required when connecting WhatsApp.'
      : replacing[field]
        ? `Enter the new ${SECRET_LABELS[field]}, or click Keep current.`
        : undefined
  const accessToken = validateSecret(
    values.access_token, WHATSAPP_LIMITS.accessTokenMaxLength, requiredMessage('access_token'),
  )
  if (accessToken) errors.access_token = accessToken
  const appSecret = validateSecret(values.app_secret, WHATSAPP_LIMITS.appSecretMaxLength, requiredMessage('app_secret'))
  if (appSecret) errors.app_secret = appSecret
  return errors
}
