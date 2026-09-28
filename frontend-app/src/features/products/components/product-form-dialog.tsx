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

  const set = <K extends keyof ProductFormValues>(key: K, value: ProductFormValues[K]) => {
    setValues((current) => ({ ...current, [key]: value }))
    // Clear that field's error as soon as the user edits it.
    setErrors((current) => ({ ...current, fields: { ...current.fields, [key]: '' } }))
  }

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const fieldErrors = validateProduct(values)
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
          length={{ current: values.description.trim().length, max: PRODUCT_LIMITS.descriptionMaxLength }}
        >
          <Textarea
            id="product-description"
            value={values.description}
            onChange={(e) => set('description', e.target.value)}
            aria-invalid={invalid('description')}
            className="max-h-48"
          />
        </FormField>

        <div className="grid gap-5 sm:grid-cols-3">
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
            id="product-quantity-available"
            label="Qty available"
            required
            error={fieldError('quantity_available')}
          >
            <Input
              id="product-quantity-available"
              type="number"
              min={0}
              max={PRODUCT_LIMITS.quantityMax}
              step={1}
              value={values.quantity_available}
              onChange={(e) => set('quantity_available', e.target.value)}
              aria-invalid={invalid('quantity_available')}
            />
          </FormField>
          <FormField
            id="product-quantity-on-hold"
            label="Qty on hold"
            required
            error={fieldError('quantity_on_hold')}
          >
            <Input
              id="product-quantity-on-hold"
              type="number"
              min={0}
              max={PRODUCT_LIMITS.quantityMax}
              step={1}
              value={values.quantity_on_hold}
              onChange={(e) => set('quantity_on_hold', e.target.value)}
              aria-invalid={invalid('quantity_on_hold')}
            />
          </FormField>
        </div>

        {isEdit && (
          <FormField id="product-quantity-sold" label="Qty sold" hint="Read-only: updated by the system.">
            <Input id="product-quantity-sold" value={product.quantity_sold} disabled readOnly />
          </FormField>
        )}

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
