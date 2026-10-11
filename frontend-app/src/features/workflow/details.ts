import type { DetailField, DetailFieldType } from './types'

// Customer details the Details collection step asks for. Limits mirror configuration-service
// `chat_app/validators.py` (`detail_field_errors`); keep them in sync.
export const DETAIL_LIMITS = {
  fieldsMax: 20,
  keyMaxLength: 40,
  labelMaxLength: 100,
  descriptionMaxLength: 300,
  textMaxLength: 2000,
  textDefaultMaxLength: 500,
} as const

const KEY_PATTERN = /^[a-z][a-z0-9_]*$/

export const DETAIL_TYPE_LABELS: Record<DetailFieldType, string> = {
  text: 'Text',
  number: 'Number',
  email: 'Email address',
}

/**
 * What both details steps ask for until the business changes them (configuration-service
 * `DEFAULT_DETAIL_FIELDS`): a name and an email, both required.
 */
export const DEFAULT_DETAIL_FIELDS: DetailField[] = [
  { key: 'name', label: 'Name', type: 'text', max_length: 150 },
  { key: 'email', label: 'Email', type: 'email' },
]

/** Common details the business can switch on or off. The first two are on by default. */
export const PRESET_DETAIL_FIELDS: DetailField[] = [
  ...DEFAULT_DETAIL_FIELDS,
  { key: 'address', label: 'Delivery address', type: 'text', max_length: 300 },
]

export function isPresetKey(key: string): boolean {
  return PRESET_DETAIL_FIELDS.some((preset) => preset.key === key)
}

/** The given fields, or the defaults when there are none. */
export function detailFieldsOrDefault(fields: DetailField[] | undefined): DetailField[] {
  return fields && fields.length > 0 ? fields : DEFAULT_DETAIL_FIELDS.map((f) => ({ ...f }))
}

/** Fixed key order, and only the keys allowed for the field's type (so JSON comparisons are stable). */
export function normalizeDetailField(field: DetailField): DetailField {
  const normalized: DetailField = { key: field.key, label: field.label, type: field.type }
  if (field.description) normalized.description = field.description
  if (field.required === false) normalized.required = false // required is the default: left out
  if (field.type === 'text' && field.max_length !== undefined) normalized.max_length = field.max_length
  if (field.type === 'number') {
    if (field.min_value !== undefined) normalized.min_value = field.min_value
    if (field.max_value !== undefined) normalized.max_value = field.max_value
  }
  return normalized
}

/** A valid, unused key from a label, e.g. "Postal code" → `postal_code` (`postal_code_2` if taken). */
export function keyFromLabel(label: string, takenKeys: Set<string>): string {
  let base = label
    .toLowerCase()
    .normalize('NFKD')
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
  if (!/^[a-z]/.test(base)) base = `field_${base}`.replace(/_+$/, '')
  base = base.slice(0, DETAIL_LIMITS.keyMaxLength - 3)
  let key = base
  for (let n = 2; takenKeys.has(key); n++) key = `${base}_${n}`
  return key
}

export function isValidDetailKey(key: string): boolean {
  return KEY_PATTERN.test(key) && key.length <= DETAIL_LIMITS.keyMaxLength
}

export function isRequiredDetail(field: DetailField): boolean {
  return field.required !== false
}

/** One line describing a field, e.g. "Number, 100000–999999" (", optional" if it is). */
export function describeDetailField(field: DetailField): string {
  const parts: string[] = [DETAIL_TYPE_LABELS[field.type]]
  if (field.type === 'text') parts.push(`max ${field.max_length ?? DETAIL_LIMITS.textDefaultMaxLength} characters`)
  if (field.type === 'number') {
    const { min_value: low, max_value: high } = field
    if (low !== undefined && high !== undefined) parts.push(`${low}–${high}`)
    else if (low !== undefined) parts.push(`at least ${low}`)
    else if (high !== undefined) parts.push(`at most ${high}`)
  }
  if (!isRequiredDetail(field)) parts.push('optional')
  return parts.join(', ')
}
