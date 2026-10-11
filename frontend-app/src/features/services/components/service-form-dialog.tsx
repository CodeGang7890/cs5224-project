import { type FormEvent, useState } from 'react'

import { ConfirmDialog } from '@/components/common/confirm-dialog'
import { FormField } from '@/components/common/form-field'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { type FormErrors, getFormErrors } from '@/lib/form-errors'
import { cn } from '@/lib/utils'

import { useProviders, useSaveService } from '../hooks/use-services'
import type { Service, ServiceInput } from '../types'
import {
  SERVICE_FIELD_LABELS,
  SERVICE_LIMITS,
  type ServiceFormValues,
  changedServiceFields,
  emptyServiceValues,
  formValuesToServiceInput,
  START_INTERVAL_PRESETS,
  exampleStartTimes,
  formatMinutes,
  formatStartInterval,
  serviceToFormValues,
  validateService,
} from '../validation'

interface ServiceFormDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** The service to edit; omit to create a new one. */
  service?: Service
}

/** Create/edit form in a dialog. Saving asks for confirmation first. */
export function ServiceFormDialog({ open, onOpenChange, service }: ServiceFormDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90svh] overflow-y-auto sm:max-w-xl">
        {/* Remounted on every open, so the form always starts from the saved values. */}
        {open && <ServiceForm service={service} onDone={() => onOpenChange(false)} />}
      </DialogContent>
    </Dialog>
  )
}

function ServiceForm({ service, onDone }: { service?: Service; onDone: () => void }) {
  const isEdit = service !== undefined
  const saveService = useSaveService()
  const providers = useProviders()
  const [values, setValues] = useState<ServiceFormValues>(service ? serviceToFormValues(service) : emptyServiceValues)
  const [errors, setErrors] = useState<FormErrors>({ fields: {} })
  const [confirmOpen, setConfirmOpen] = useState(false)

  const input = formValuesToServiceInput(values)
  const changes = isEdit ? changedServiceFields(service, input) : input
  const changedLabels = Object.keys(changes).map((key) => SERVICE_FIELD_LABELS[key as keyof ServiceInput])
  const hasChanges = changedLabels.length > 0

  const set = <K extends keyof ServiceFormValues>(key: K, value: ServiceFormValues[K]) => {
    setValues((current) => ({ ...current, [key]: value }))
    setErrors((current) => ({ ...current, fields: { ...current.fields, [key]: '' } }))
  }

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const fieldErrors = validateService(values)
    setErrors({ fields: fieldErrors as Record<string, string> })
    if (Object.keys(fieldErrors).length === 0 && hasChanges) setConfirmOpen(true)
  }

  const handleConfirm = () => {
    saveService.mutate(isEdit ? { id: service.id, input: changes } : { input }, {
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

  const fieldError = (key: keyof ServiceFormValues) => errors.fields[key] || undefined
  const invalid = (key: keyof ServiceFormValues) => (fieldError(key) ? true : undefined)
  const duration = Number(values.duration_minutes)
  const buffer = Number(values.buffer_minutes)
  const interval = Number(values.start_interval_minutes)
  // A value other than the presets is edited in the custom box.
  const [customInterval, setCustomInterval] = useState(
    () => !START_INTERVAL_PRESETS.some((preset) => String(preset) === values.start_interval_minutes),
  )

  return (
    <>
      <form onSubmit={handleSubmit} noValidate className="grid gap-5">
        <DialogHeader>
          <DialogTitle>{isEdit ? 'Edit service' : 'Add service'}</DialogTitle>
          <DialogDescription>
            {isEdit ? `Update the details of “${service.name}”.` : 'Add something customers can book a time for.'}
          </DialogDescription>
        </DialogHeader>

        <FormField
          id="service-name"
          label="Name"
          required
          error={fieldError('name')}
          length={{ current: values.name.trim().length, max: SERVICE_LIMITS.nameMaxLength }}
        >
          <Input id="service-name" value={values.name} onChange={(e) => set('name', e.target.value)} aria-invalid={invalid('name')} autoFocus />
        </FormField>

        <FormField
          id="service-description"
          label="Description"
          error={fieldError('description')}
          tooltip="A short summary of the service. The chat assistant tells customers this when they ask what it is."
          length={{ current: values.description.trim().length, max: SERVICE_LIMITS.descriptionMaxLength }}
        >
          <Textarea
            id="service-description"
            value={values.description}
            onChange={(e) => set('description', e.target.value)}
            aria-invalid={invalid('description')}
            className="max-h-32"
          />
        </FormField>

        <FormField
          id="service-information"
          label="Information"
          error={fieldError('information')}
          hint="Extra details for the chat assistant. Customers don't see it as written."
          tooltip="What's included, what to bring, locations, how many people, FAQs about it, etc. The chat assistant answers specific questions from it."
          length={{ current: values.information.trim().length, max: SERVICE_LIMITS.informationMaxLength }}
        >
          <Textarea
            id="service-information"
            value={values.information}
            onChange={(e) => set('information', e.target.value)}
            aria-invalid={invalid('information')}
            className="min-h-24 max-h-60"
          />
        </FormField>

        <div className="grid gap-5 sm:grid-cols-3">
          <FormField id="service-price" label="Price" required error={fieldError('price')} hint="e.g. 180.00">
            <Input id="service-price" inputMode="decimal" value={values.price} onChange={(e) => set('price', e.target.value)} aria-invalid={invalid('price')} />
          </FormField>
          <FormField
            id="service-duration"
            label="Duration (min)"
            required
            error={fieldError('duration_minutes')}
            hint={!fieldError('duration_minutes') && duration > 0 ? formatMinutes(duration) : undefined}
            tooltip="How long the service takes, with the customer. Bookings are in 15-minute blocks, so use a multiple of 15."
          >
            <Input
              id="service-duration"
              type="number"
              min={SERVICE_LIMITS.durationMinMinutes}
              max={SERVICE_LIMITS.durationMaxMinutes}
              step={SERVICE_LIMITS.stepMinutes}
              value={values.duration_minutes}
              onChange={(e) => set('duration_minutes', e.target.value)}
              aria-invalid={invalid('duration_minutes')}
            />
          </FormField>
          <FormField
            id="service-buffer"
            label="Buffer (min)"
            required
            error={fieldError('buffer_minutes')}
            hint={!fieldError('buffer_minutes') && buffer > 0 ? `${formatMinutes(buffer)} after` : 'None'}
            tooltip="Time blocked after each booking without the customer (e.g. to tidy up or travel): the next booking can only start after it. A multiple of 15."
          >
            <Input
              id="service-buffer"
              type="number"
              min={0}
              max={SERVICE_LIMITS.bufferMaxMinutes}
              step={SERVICE_LIMITS.stepMinutes}
              value={values.buffer_minutes}
              onChange={(e) => set('buffer_minutes', e.target.value)}
              aria-invalid={invalid('buffer_minutes')}
            />
          </FormField>
        </div>

        <fieldset className="grid gap-2">
          <legend className="text-sm font-medium">Bookings start every</legend>
          <p className="text-muted-foreground text-xs">
            Which start times customers can book, counted from midnight. For a 1-hour service open 9am to 11am: every
            15 min allows 9:15–10:15, every 30 min only 9:00, 9:30 or 10:00, every hour only 9:00 or 10:00.
          </p>
          <div className="flex flex-wrap items-center gap-1" role="radiogroup" aria-label="Bookings start every">
            {START_INTERVAL_PRESETS.map((preset) => {
              const selected = !customInterval && interval === preset
              return (
                <button
                  key={preset}
                  type="button"
                  role="radio"
                  aria-checked={selected}
                  onClick={() => {
                    setCustomInterval(false)
                    set('start_interval_minutes', String(preset))
                  }}
                  className={cn(
                    'rounded-md border px-3 py-1.5 text-sm',
                    selected ? 'bg-primary text-primary-foreground border-primary' : 'hover:bg-muted',
                  )}
                >
                  {preset === 60 ? '1 hour' : `${preset} min`}
                </button>
              )
            })}
            <button
              type="button"
              role="radio"
              aria-checked={customInterval}
              onClick={() => setCustomInterval(true)}
              className={cn(
                'rounded-md border px-3 py-1.5 text-sm',
                customInterval ? 'bg-primary text-primary-foreground border-primary' : 'hover:bg-muted',
              )}
            >
              Custom
            </button>
          </div>
          {customInterval && (
            <FormField id="service-start-interval" label="Minutes between start times" required error={fieldError('start_interval_minutes')}>
              <Input
                id="service-start-interval"
                type="number"
                className="w-40"
                min={SERVICE_LIMITS.startIntervalMinMinutes}
                max={SERVICE_LIMITS.startIntervalMaxMinutes}
                step={SERVICE_LIMITS.stepMinutes}
                value={values.start_interval_minutes}
                onChange={(e) => set('start_interval_minutes', e.target.value)}
                aria-invalid={invalid('start_interval_minutes')}
              />
            </FormField>
          )}
          {!customInterval && fieldError('start_interval_minutes') && (
            <p className="text-destructive text-xs">{fieldError('start_interval_minutes')}</p>
          )}
          {!fieldError('start_interval_minutes') && exampleStartTimes(interval) && (
            <p className="text-muted-foreground text-xs">
              Starts {formatStartInterval(interval)}: {exampleStartTimes(interval)}
            </p>
          )}
        </fieldset>

        <fieldset className="grid gap-2">
          <legend className="text-sm font-medium">Who can do it</legend>
          <p className="text-muted-foreground text-xs">
            The service providers (e.g. photographers) who do this service. A booking goes to the first one free at
            that time, by their schedule.
          </p>
          {providers.isPending ? (
            <p className="text-muted-foreground text-sm">Loading…</p>
          ) : providers.isError ? (
            <p className="text-destructive text-sm">Couldn't load your service providers.</p>
          ) : providers.data.results.length === 0 ? (
            <p className="text-muted-foreground rounded-md border border-dashed p-3 text-sm">
              No service providers yet: add one in the Service providers section, then link them here.
            </p>
          ) : (
            <ul className="grid gap-1 rounded-md border p-2">
              {providers.data.results.map((provider) => (
                <li key={provider.id}>
                  <label className="hover:bg-muted/50 flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-sm">
                    <input
                      type="checkbox"
                      checked={values.service_providers.includes(provider.id)}
                      onChange={(e) =>
                        set(
                          'service_providers',
                          e.target.checked
                            ? [...values.service_providers, provider.id]
                            : values.service_providers.filter((id) => id !== provider.id),
                        )
                      }
                    />
                    <span className="font-medium">{provider.name}</span>
                    {!provider.is_active && <span className="text-muted-foreground text-xs">(inactive)</span>}
                  </label>
                </li>
              ))}
            </ul>
          )}
          {fieldError('service_providers') && <p className="text-destructive text-xs">{fieldError('service_providers')}</p>}
        </fieldset>

        <div className="flex items-center justify-between gap-4 rounded-md border p-3">
          <div className="grid gap-1">
            <label htmlFor="service-is-active" className="text-sm font-medium">
              Active
            </label>
            <p className="text-muted-foreground text-xs">Inactive services can't be booked.</p>
          </div>
          <Switch id="service-is-active" checked={values.is_active} onCheckedChange={(checked) => set('is_active', checked)} />
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
            {isEdit ? 'Save changes' : 'Add service'}
          </Button>
        </DialogFooter>
      </form>

      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title={isEdit ? 'Save changes?' : 'Add this service?'}
        description={
          isEdit ? (
            <>
              Update <strong>{changedLabels.join(', ')}</strong> of “{service.name}”. Existing bookings keep their times.
            </>
          ) : (
            <>“{input.name}” will be added to your services.</>
          )
        }
        confirmLabel={isEdit ? 'Save changes' : 'Add service'}
        pendingLabel="Saving…"
        isPending={saveService.isPending}
        onConfirm={handleConfirm}
      />
    </>
  )
}
