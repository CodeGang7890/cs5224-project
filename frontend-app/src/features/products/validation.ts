import type { Product, ProductInput } from './types'

// Mirrors configuration-service product_app/models.py. The backend validates too; this just
// gives instant feedback.
export const PRODUCT_LIMITS = {
  nameMaxLength: 150,
  descriptionMaxLength: 300,
  informationMaxLength: 5000,
  priceMax: 99_999_999.99,
  quantityMax: 1_000_000,
} as const

/** Form state: number fields are kept as strings while the user types. */
export interface ProductFormValues {
  name: string
  description: string
  information: string
  price: string
  quantity_available: string
  quantity_on_hold: string
  is_active: boolean
}

export const PRODUCT_FIELD_LABELS: Record<keyof ProductInput, string> = {
  name: 'Name',
  description: 'Description',
  information: 'Information',
  price: 'Price',
  quantity_available: 'Quantity available',
  quantity_on_hold: 'Quantity on hold',
  is_active: 'Active',
}

export const emptyProductValues: ProductFormValues = {
  name: '',
  description: '',
  information: '',
  price: '',
  quantity_available: '0',
  quantity_on_hold: '0',
  is_active: true,
}

export function productToFormValues(product: Product): ProductFormValues {
  return {
    name: product.name,
    description: product.description,
    information: product.information,
    price: product.price,
    quantity_available: String(product.quantity_available),
    quantity_on_hold: String(product.quantity_on_hold),
    is_active: product.is_active,
  }
}

export function formValuesToProductInput(values: ProductFormValues): ProductInput {
  return {
    name: values.name.trim(),
    description: values.description.trim(),
    information: values.information.trim(),
    price: Number(values.price).toFixed(2),
    quantity_available: Number(values.quantity_available),
    quantity_on_hold: Number(values.quantity_on_hold),
    is_active: values.is_active,
  }
}

const PRICE_PATTERN = /^\d+(\.\d{1,2})?$/
const INTEGER_PATTERN = /^\d+$/

function validateQuantity(value: string): string | undefined {
  if (value.trim() === '') return 'Required.'
  if (!INTEGER_PATTERN.test(value.trim())) return 'Must be a whole number of 0 or more.'
  if (Number(value) > PRODUCT_LIMITS.quantityMax) {
    return `Must be at most ${PRODUCT_LIMITS.quantityMax.toLocaleString()}.`
  }
  return undefined
}

/** Returns an error message per invalid field (empty object = valid). */
export function validateProduct(values: ProductFormValues): Partial<Record<keyof ProductInput, string>> {
  const errors: Partial<Record<keyof ProductInput, string>> = {}

  const name = values.name.trim()
  if (!name) errors.name = 'Name is required.'
  else if (name.length > PRODUCT_LIMITS.nameMaxLength) {
    errors.name = `Must be at most ${PRODUCT_LIMITS.nameMaxLength} characters.`
  }

  if (values.description.trim().length > PRODUCT_LIMITS.descriptionMaxLength) {
    errors.description = `Must be at most ${PRODUCT_LIMITS.descriptionMaxLength.toLocaleString()} characters.`
  }
  if (values.information.trim().length > PRODUCT_LIMITS.informationMaxLength) {
    errors.information = `Must be at most ${PRODUCT_LIMITS.informationMaxLength.toLocaleString()} characters.`
  }

  const price = values.price.trim()
  if (!price) errors.price = 'Price is required.'
  else if (!PRICE_PATTERN.test(price)) errors.price = 'Enter a number of 0 or more, with up to 2 decimal places.'
  else if (Number(price) > PRODUCT_LIMITS.priceMax) {
    errors.price = `Must be at most ${PRODUCT_LIMITS.priceMax.toLocaleString(undefined, { minimumFractionDigits: 2 })}.`
  }

  const available = validateQuantity(values.quantity_available)
  if (available) errors.quantity_available = available
  const onHold = validateQuantity(values.quantity_on_hold)
  if (onHold) errors.quantity_on_hold = onHold

  return errors
}

/** Only the fields that differ from the saved product (for PATCH). */
export function changedProductFields(original: Product, input: ProductInput): Partial<ProductInput> {
  const changes: Partial<ProductInput> = {}
  for (const key of Object.keys(input) as (keyof ProductInput)[]) {
    const before = key === 'price' ? Number(original.price).toFixed(2) : original[key]
    if (before !== input[key]) Object.assign(changes, { [key]: input[key] })
  }
  return changes
}
