import { isValidAvailability } from './availability'
import type { Service, ServiceInput, WeeklyAvailability, WeeklyAvailabilityInput } from './types'

// Mirrors configuration-service product_app/models.py. The backend validates too; this just
// gives instant feedback.
export const SERVICE_LIMITS = {
  nameMaxLength: 150,
  descriptionMaxLength: 300,
  informationMaxLength: 5000,
  priceMax: 99_999_999.99,
  durationMinMinutes: 15,
  durationMaxMinutes: 1440,
  bufferMaxMinutes: 1440,
  stepMinutes: 15,
  availabilityNameMaxLength: 150,
} as const

/** Form state: number fields are kept as strings while the user types. */
export interface ServiceFormValues {
  name: string
  description: string
  information: string
  price: string
  duration_minutes: string
  buffer_minutes: string
  weekly_availability: number[]
  is_active: boolean
}

export const SERVICE_FIELD_LABELS: Record<keyof ServiceInput, string> = {
  name: 'Name',
  description: 'Description',
  information: 'Information',
  price: 'Price',
  duration_minutes: 'Duration',
  buffer_minutes: 'Buffer',
  weekly_availability: 'Availability',
  is_active: 'Active',
}

export const emptyServiceValues: ServiceFormValues = {
  name: '',
  description: '',
  information: '',
  price: '',
  duration_minutes: '60',
  buffer_minutes: '0',
  weekly_availability: [],
  is_active: true,
}

export function serviceToFormValues(service: Service): ServiceFormValues {
  return {
    name: service.name,
    description: service.description,
    information: service.information,
    price: service.price,
    duration_minutes: String(service.duration_minutes),
    buffer_minutes: String(service.buffer_minutes),
    weekly_availability: [...service.weekly_availability],
    is_active: service.is_active,
  }
}

export function formValuesToServiceInput(values: ServiceFormValues): ServiceInput {
  return {
    name: values.name.trim(),
    description: values.description.trim(),
    information: values.information.trim(),
    price: Number(values.price).toFixed(2),
    duration_minutes: Number(values.duration_minutes),
    buffer_minutes: Number(values.buffer_minutes),
    weekly_availability: [...values.weekly_availability].sort((a, b) => a - b),
    is_active: values.is_active,
  }
}

const PRICE_PATTERN = /^\d+(\.\d{1,2})?$/
const INTEGER_PATTERN = /^\d+$/

function validateMinutes(value: string, min: number, max: number): string | undefined {
  if (!INTEGER_PATTERN.test(value.trim())) return 'Enter a whole number of minutes.'
  const minutes = Number(value)
  if (minutes < min || minutes > max) return `Must be from ${min} to ${max.toLocaleString()} minutes.`
  if (minutes % SERVICE_LIMITS.stepMinutes) return `Must be a multiple of ${SERVICE_LIMITS.stepMinutes} minutes.`
  return undefined
}

/** Returns an error message per invalid field (empty object = valid). */
export function validateService(values: ServiceFormValues): Partial<Record<keyof ServiceInput, string>> {
  const errors: Partial<Record<keyof ServiceInput, string>> = {}
  const name = values.name.trim()
  if (!name) errors.name = 'Name is required.'
  else if (name.length > SERVICE_LIMITS.nameMaxLength) errors.name = `Must be at most ${SERVICE_LIMITS.nameMaxLength} characters.`
  if (values.description.trim().length > SERVICE_LIMITS.descriptionMaxLength) {
    errors.description = `Must be at most ${SERVICE_LIMITS.descriptionMaxLength} characters.`
  }
  if (values.information.trim().length > SERVICE_LIMITS.informationMaxLength) {
    errors.information = `Must be at most ${SERVICE_LIMITS.informationMaxLength.toLocaleString()} characters.`
  }
  const price = values.price.trim()
  if (!price) errors.price = 'Price is required.'
  else if (!PRICE_PATTERN.test(price)) errors.price = 'Enter a number of 0 or more, with up to 2 decimal places.'
  else if (Number(price) > SERVICE_LIMITS.priceMax) errors.price = 'Too large.'
  const duration = validateMinutes(values.duration_minutes, SERVICE_LIMITS.durationMinMinutes, SERVICE_LIMITS.durationMaxMinutes)
  if (duration) errors.duration_minutes = duration
  const buffer = validateMinutes(values.buffer_minutes, 0, SERVICE_LIMITS.bufferMaxMinutes)
  if (buffer) errors.buffer_minutes = buffer
  return errors
}

/** Only the fields that differ from the saved service (for PATCH). */
export function changedServiceFields(original: Service, input: ServiceInput): Partial<ServiceInput> {
  const changes: Partial<ServiceInput> = {}
  for (const key of Object.keys(input) as (keyof ServiceInput)[]) {
    const before =
      key === 'price'
        ? Number(original.price).toFixed(2)
        : key === 'weekly_availability'
          ? [...original.weekly_availability].sort((a, b) => a - b)
          : original[key]
    if (JSON.stringify(before) !== JSON.stringify(input[key])) Object.assign(changes, { [key]: input[key] })
  }
  return changes
}

/** Errors in a weekly availability form (empty object = valid). */
export function validateAvailability(input: WeeklyAvailabilityInput): Partial<Record<keyof WeeklyAvailabilityInput, string>> {
  const errors: Partial<Record<keyof WeeklyAvailabilityInput, string>> = {}
  if (!input.name.trim()) errors.name = 'Name is required.'
  else if (input.name.trim().length > SERVICE_LIMITS.availabilityNameMaxLength) {
    errors.name = `Must be at most ${SERVICE_LIMITS.availabilityNameMaxLength} characters.`
  }
  if (!isValidAvailability(input.availability)) errors.availability = 'The calendar is invalid.'
  return errors
}

/** Only the changed fields of a weekly availability (for PATCH). */
export function changedAvailabilityFields(
  original: WeeklyAvailability,
  input: WeeklyAvailabilityInput,
): Partial<WeeklyAvailabilityInput> {
  const changes: Partial<WeeklyAvailabilityInput> = {}
  if (original.name !== input.name) changes.name = input.name
  if (original.availability !== input.availability) changes.availability = input.availability
  return changes
}

/** "1 h 30 min", "45 min", "2 h". */
export function formatMinutes(minutes: number): string {
  const hours = Math.floor(minutes / 60)
  const rest = minutes % 60
  if (!hours) return `${rest} min`
  return rest ? `${hours} h ${rest} min` : `${hours} h`
}
