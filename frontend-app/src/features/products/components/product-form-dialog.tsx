import { type FormEvent, useState } from 'react'

import { ConfirmDialog } from '@/components/common/confirm-dialog'
import { FormField } from '@/components/common/form-field'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { type FormErrors, getFormErrors } from '@/lib/form-errors'

import { useSaveProduct } from '../hooks/use-products'
import type { Product, ProductInput } from '../types'
import {
  PRODUCT_FIELD_LABELS,
  PRODUCT_LIMITS,
  type ProductFormValues,
  changedProductFields,
  emptyProductValues,
  formValuesToProductInput,
  minTotalQuantity,
  productToFormValues,
  validateProduct,
} from '../validation'

interface ProductFormDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** The product to edit; omit to create a new one. */
  product?: Product
}

/** Create/edit form in a dialog. Saving asks for confirmation first. */
export function ProductFormDialog({ open, onOpenChange, product }: ProductFormDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90svh] overflow-y-auto sm:max-w-xl">
        {/* Remounted on every open, so the form always starts from the saved values. */}
        {open && <ProductForm product={product} onDone={() => onOpenChange(false)} />}
      </DialogContent>
    </Dialog>
  )
}

function ProductForm({ product, onDone }: { product?: Product; onDone: () => void }) {
  const isEdit = product !== undefined
  const saveProduct = useSaveProduct()
  const [values, setValues] = useState<ProductFormValues>(
    product ? productToFormValues(product) : emptyProductValues,
  )
  const [errors, setErrors] = useState<FormErrors>({ fields: {} })
  const [confirmOpen, setConfirmOpen] = useState(false)

  const input = formValuesToProductInput(values)
  const changes = isEdit ? changedProductFields(product, input) : input
  const changedLabels = Object.keys(changes).map((key) => PRODUCT_FIELD_LABELS[key as keyof ProductInput])
  const hasChanges = changedLabels.length > 0
  const minTotal = product ? minTotalQuantity(product) : 0

  const set = <K extends keyof ProductFormValues>(key: K, value: ProductFormValues[K]) => {
    setValues((current) => ({ ...current, [key]: value }))
    // Clear that field's error as soon as the user edits it.
    setErrors((current) => ({ ...current, fields: { ...current.fields, [key]: '' } }))
  }

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const fieldErrors = validateProduct(values, product)
    setErrors({ fields: fieldErrors as Record<string, string> })
    if (Object.keys(fieldErrors).length === 0 && hasChanges) setConfirmOpen(true)
  }

  const handleConfirm = () => {
    saveProduct.mutate(isEdit ? { id: product.id, input: changes } : { input }, {
      onSuccess: () => {
        setConfirmOpen(false)
        onDone()
      },
      onError: (error) => {
        setConfirmOpen(false)
        setErrors(getFormErrors(error))
      },
    })
  }

  const fieldError = (key: keyof ProductFormValues) => errors.fields[key] || undefined
  const invalid = (key: keyof ProductFormValues) => (fieldError(key) ? true : undefined)

  return (
    <>
      <form onSubmit={handleSubmit} noValidate className="grid gap-5">
        <DialogHeader>
          <DialogTitle>{isEdit ? 'Edit product' : 'Add product'}</DialogTitle>
          <DialogDescription>
            {isEdit ? `Update the details of “${product.name}”.` : 'Add a new product to your business.'}
          </DialogDescription>
        </DialogHeader>

        <FormField
          id="product-name"
          label="Name"
          required
          error={fieldError('name')}
          length={{ current: values.name.trim().length, max: PRODUCT_LIMITS.nameMaxLength }}
        >
          <Input
            id="product-name"
            value={values.name}
            onChange={(e) => set('name', e.target.value)}
            aria-invalid={invalid('name')}
            autoFocus
          />
        </FormField>

        <FormField
          id="product-description"
          label="Description"
          error={fieldError('description')}
          tooltip="A short summary of the product. The chat assistant tells customers this when they ask what the product is, so keep it to the key points."
          length={{ current: values.description.trim().length, max: PRODUCT_LIMITS.descriptionMaxLength }}
        >
          <Textarea
            id="product-description"
            value={values.description}
            onChange={(e) => set('description', e.target.value)}
            aria-invalid={invalid('description')}
            className="max-h-32"
          />
        </FormField>

        <FormField
          id="product-information"
          label="Information"
          error={fieldError('information')}
          hint="Extra details for the chat assistant. Customers don't see it as written."
          tooltip="Everything else the chat assistant may need to answer questions about this product: ingredients, sizes, options, allergens, care instructions, FAQs about it, etc. It's only used when a customer asks something the description doesn't cover, and the assistant answers from it."
          length={{ current: values.information.trim().length, max: PRODUCT_LIMITS.informationMaxLength }}
        >
          <Textarea
            id="product-information"
            value={values.information}
            onChange={(e) => set('information', e.target.value)}
            aria-invalid={invalid('information')}
            className="min-h-32 max-h-72"
          />
        </FormField>

        <div className="grid gap-5 sm:grid-cols-2">
          <FormField id="product-price" label="Price" required error={fieldError('price')} hint="e.g. 12.50">
            <Input
              id="product-price"
              inputMode="decimal"
              value={values.price}
              onChange={(e) => set('price', e.target.value)}
              aria-invalid={invalid('price')}
            />
          </FormField>
          <FormField
            id="product-total-quantity"
            label="Total quantity"
            required
            error={fieldError('total_quantity')}
            hint={isEdit ? `At least ${minTotal.toLocaleString()} (on hold + sold).` : undefined}
            tooltip="How many you have in total, including those on hold or sold in orders. Raise it when you get more stock; lower it only as far as what's on hold or sold. Available, on hold and sold are worked out from your orders."
          >
            <Input
              id="product-total-quantity"
              type="number"
              min={minTotal}
              max={PRODUCT_LIMITS.quantityMax}
              step={1}
              value={values.total_quantity}
              onChange={(e) => set('total_quantity', e.target.value)}
              aria-invalid={invalid('total_quantity')}
            />
          </FormField>
        </div>

        {isEdit && <StockSummary product={product} totalQuantity={values.total_quantity} />}

        <div className="flex items-center justify-between gap-4 rounded-md border p-3">
          <div className="grid gap-1">
            <label htmlFor="product-is-active" className="text-sm font-medium">
              Active
            </label>
            <p className="text-muted-foreground text-xs">Inactive products are hidden from customers.</p>
          </div>
          <Switch
            id="product-is-active"
            checked={values.is_active}
            onCheckedChange={(checked) => set('is_active', checked)}
          />
        </div>

        {errors.form && (
          <p role="alert" className="text-destructive text-sm">
            {errors.form}
          </p>
        )}

        <DialogFooter>
          <Button type="button" variant="outline" onClick={onDone}>
            Cancel
          </Button>
          <Button type="submit" disabled={!hasChanges}>
            {isEdit ? 'Save changes' : 'Add product'}
          </Button>
        </DialogFooter>
      </form>

      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title={isEdit ? 'Save changes?' : 'Add this product?'}
        description={
          isEdit ? (
            <>
              Update <strong>{changedLabels.join(', ')}</strong> of “{product.name}”.
            </>
          ) : (
            <>“{input.name}” will be added to your products.</>
          )
        }
        confirmLabel={isEdit ? 'Save changes' : 'Add product'}
        pendingLabel="Saving…"
        isPending={saveProduct.isPending}
        onConfirm={handleConfirm}
      />
    </>
  )
}

const quantityFormat = new Intl.NumberFormat()

/** The product's quantities derived from its orders, and what's available with the total being typed. */
function StockSummary({ product, totalQuantity }: { product: Product; totalQuantity: string }) {
  const total = Number(totalQuantity)
  const changed = /^\d+$/.test(totalQuantity.trim()) && total !== product.total_quantity
  const availableAfter = total - minTotalQuantity(product)
  const stats = [
    { label: 'Available', value: product.quantity_available },
    { label: 'On hold', value: product.quantity_on_hold, hint: 'In orders pending payment or paid' },
    { label: 'Sold', value: product.quantity_sold, hint: 'In completed orders' },
  ]
  return (
    <div className="grid gap-2 rounded-md border p-3">
      <dl className="grid grid-cols-3 gap-3">
        {stats.map((stat) => (
          <div key={stat.label} className="grid gap-0.5" title={stat.hint}>
            <dt className="text-muted-foreground text-xs">{stat.label}</dt>
            <dd className="text-sm font-medium tabular-nums">{quantityFormat.format(stat.value)}</dd>
          </div>
        ))}
      </dl>
      <p className="text-muted-foreground text-xs">
        {changed && availableAfter >= 0
          ? `After saving: ${quantityFormat.format(availableAfter)} available.`
          : 'Worked out from your orders. Change the total quantity to add or remove stock.'}
      </p>
    </div>
  )
}
