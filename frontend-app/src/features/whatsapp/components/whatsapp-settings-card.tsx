import { type FormEvent, type ReactNode, useState } from 'react'
import { Check, Copy, MessageCircle, Pencil, Phone, Unplug } from 'lucide-react'

import { ConfirmDialog } from '@/components/common/confirm-dialog'
import { FormField } from '@/components/common/form-field'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { LoginDialog } from '@/features/auth'
import { type FormErrors, getFormErrors } from '@/lib/form-errors'
import { selectIsAuthenticated, useAuthStore } from '@/stores/auth-store'

import {
  useDeleteWhatsAppConfiguration,
  useSaveWhatsAppConfiguration,
  useWhatsAppConfiguration,
} from '../hooks/use-whatsapp-configuration'
import type { WhatsAppConfiguration } from '../types'
import {
  SECRET_LABELS,
  type SecretField,
  WHATSAPP_LIMITS,
  type WhatsAppFormValues,
  changedWhatsAppFields,
  formValuesToWhatsAppInput,
  validateWhatsApp,
  whatsAppToFormValues,
} from '../validation'

/**
 * Connects the business's WhatsApp Business number (from the owner's own Meta app), and shows the
 * Callback URL and verify token to enter in Meta's webhook settings.
 */
export function WhatsAppSettingsCard() {
  const isAuthenticated = useAuthStore(selectIsAuthenticated)
  const { data: config, isPending, isError, error, refetch } = useWhatsAppConfiguration(isAuthenticated)
  const isConnected = Boolean(config)

  return (
    <Card className="max-w-2xl">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <MessageCircle className="size-5" /> WhatsApp
        </CardTitle>
        <CardDescription>
          Connect your WhatsApp Business number, so customers' messages reach your assistant.
        </CardDescription>
        {isAuthenticated && !isPending && !isError && (
          <CardAction>
            {isConnected ? (
              <Badge variant="outline" className="border-emerald-500/50 text-emerald-700 dark:text-emerald-400">
                Connected
              </Badge>
            ) : (
              <Badge variant="outline">Not connected</Badge>
            )}
          </CardAction>
        )}
      </CardHeader>
      <CardContent>
        {!isAuthenticated ? (
          <div className="flex flex-wrap items-center gap-3">
            <p className="text-muted-foreground text-sm">Log in to connect WhatsApp.</p>
            <LoginDialog />
          </div>
        ) : isPending ? (
          <div className="grid gap-3">
            <Skeleton className="h-9 w-full" />
            <Skeleton className="h-9 w-full" />
            <Skeleton className="h-9 w-full" />
          </div>
        ) : isError ? (
          error.status === 403 ? (
            <p className="text-muted-foreground text-sm">
              Your account isn't linked to a business, so it can't connect WhatsApp.
            </p>
          ) : (
            <div className="flex flex-col items-start gap-3">
              <p className="text-destructive text-sm">Couldn't load your WhatsApp settings: {error.message}</p>
              <Button variant="outline" size="sm" onClick={() => refetch()}>
                Try again
              </Button>
            </div>
          )
        ) : (
          <div className="grid gap-6">
            {config && <ConnectedNumber config={config} />}
            {config && <WebhookSetup config={config} />}
            {/* Remounted after each save, so the form starts from the saved values with empty secrets. */}
            <WhatsAppForm key={config?.last_updated ?? 'new'} config={config ?? null} />
          </div>
        )}
      </CardContent>
    </Card>
  )
}

/**
 * Not connected: an editable form to connect. Connected: the saved details are shown locked;
 * **Edit** unlocks them, then **Save changes** (with confirmation) or **Cancel**.
 */
function WhatsAppForm({ config }: { config: WhatsAppConfiguration | null }) {
  const isConnected = config !== null
  const saveConfig = useSaveWhatsAppConfiguration()
  const [values, setValues] = useState<WhatsAppFormValues>(() => whatsAppToFormValues(config))
  const [errors, setErrors] = useState<FormErrors>({ fields: {} })
  const [confirmOpen, setConfirmOpen] = useState(false)
  // Starts locked when connected. A successful save remounts the form, which locks it again.
  const [editing, setEditing] = useState(!isConnected)
  const locked = !editing
  // Connected: a saved secret is shown masked until the owner clicks Replace to enter a new one.
  const [replacing, setReplacing] = useState<Record<SecretField, boolean>>({ access_token: false, app_secret: false })

  const input = formValuesToWhatsAppInput(values)
  const changed = changedWhatsAppFields(config, input)
  const hasChanges = changed.length > 0
  // Connecting needs all three values, so Connect stays disabled until each one is filled in.
  const allFilled = Object.values(values).every((value) => value.trim() !== '')

  const set = (key: keyof WhatsAppFormValues, value: string) => {
    setValues((current) => ({ ...current, [key]: value }))
    // Clear that field's error as soon as the user edits it.
    setErrors((current) => ({ ...current, fields: { ...current.fields, [key]: '' } }))
  }

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const fieldErrors = validateWhatsApp(values, isConnected, replacing)
    setErrors({ fields: fieldErrors as Record<string, string> })
    if (Object.keys(fieldErrors).length === 0 && hasChanges) setConfirmOpen(true)
  }

  const cancelEditing = () => {
    setValues(whatsAppToFormValues(config))
    setErrors({ fields: {} })
    setReplacing({ access_token: false, app_secret: false })
    setEditing(false)
  }

  /** Replace: show an empty input for a new secret. Keep current: back to the saved one. */
  const setReplacingSecret = (field: SecretField, value: boolean) => {
    setReplacing((current) => ({ ...current, [field]: value }))
    if (!value) set(field, '')
  }

  const secretInput = (field: SecretField, id: string, maxLength: number) => {
    const input = (
      <Input
        id={id}
        type="password"
        maxLength={maxLength}
        value={values[field]}
        onChange={(e) => set(field, e.target.value)}
        placeholder={isConnected ? `Paste the new ${SECRET_LABELS[field]}` : undefined}
        aria-invalid={invalid(field)}
        autoComplete="new-password"
        autoFocus={isConnected}
      />
    )
    if (!isConnected) return input
    if (!replacing[field]) {
      return (
        <SavedSecret id={id} label={SECRET_LABELS[field]}>
          {!locked && (
            <Button type="button" variant="outline" onClick={() => setReplacingSecret(field, true)}>
              Replace
            </Button>
          )}
        </SavedSecret>
      )
    }
    return (
      <div className="flex gap-2">
        {input}
        <Button type="button" variant="ghost" onClick={() => setReplacingSecret(field, false)}>
          Keep current
        </Button>
      </div>
    )
  }

  const handleConfirm = () => {
    saveConfig.mutate(input, {
      // On success the card remounts this form (new `last_updated`), clearing the secrets.
      onSuccess: () => setConfirmOpen(false),
      onError: (error) => {
        setConfirmOpen(false)
        setErrors(getFormErrors(error))
      },
    })
  }

  const fieldError = (key: keyof WhatsAppFormValues) => errors.fields[key] || undefined
  const invalid = (key: keyof WhatsAppFormValues) => (fieldError(key) ? true : undefined)

  return (
    <>
      <form onSubmit={handleSubmit} noValidate className="grid gap-5">
        {isConnected && <h3 className="text-sm font-semibold">Connection details</h3>}

        <FormField
          id="whatsapp-phone-number-id"
          label="Phone Number ID"
          required
          error={fieldError('phone_number_id')}
          hint="In your Meta app: WhatsApp → API Setup, the digits under your phone number (not the number itself)."
        >
          <Input
            id="whatsapp-phone-number-id"
            disabled={locked}
            inputMode="numeric"
            maxLength={WHATSAPP_LIMITS.phoneNumberIdMaxLength}
            value={values.phone_number_id}
            onChange={(e) => set('phone_number_id', e.target.value)}
            aria-invalid={invalid('phone_number_id')}
            autoComplete="off"
          />
        </FormField>

        <FormField
          id="whatsapp-access-token"
          label="Access token"
          required={!isConnected || replacing.access_token}
          error={fieldError('access_token')}
          hint="A permanent System User token (Business Settings → System users), used to send replies. The token on API Setup expires after 24 hours."
        >
          {secretInput('access_token', 'whatsapp-access-token', WHATSAPP_LIMITS.accessTokenMaxLength)}
        </FormField>

        <FormField
          id="whatsapp-app-secret"
          label="App Secret"
          required={!isConnected || replacing.app_secret}
          error={fieldError('app_secret')}
          hint="In your Meta app: App settings → Basic. Used to check that messages really come from Meta."
        >
          {secretInput('app_secret', 'whatsapp-app-secret', WHATSAPP_LIMITS.appSecretMaxLength)}
        </FormField>

        <p className="text-muted-foreground text-xs">
          These details are checked with Meta before saving. The access token and App Secret are stored
          encrypted and are never shown again.
        </p>

        {errors.form && (
          <p role="alert" className="text-destructive text-sm">
            {errors.form}
          </p>
        )}

        <div className="flex flex-wrap items-center justify-between gap-2">
          {!isConnected ? (
            <Button type="submit" disabled={!allFilled}>
              Connect WhatsApp
            </Button>
          ) : locked ? (
            <>
              <Button type="button" variant="outline" onClick={() => setEditing(true)}>
                <Pencil /> Edit
              </Button>
              <DisconnectButton />
            </>
          ) : (
            <div className="flex gap-2">
              <Button type="submit" disabled={!hasChanges}>
                Save changes
              </Button>
              <Button type="button" variant="outline" onClick={cancelEditing} disabled={saveConfig.isPending}>
                Cancel
              </Button>
            </div>
          )}
        </div>
      </form>

      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title={isConnected ? 'Save changes?' : 'Connect WhatsApp?'}
        description={
          isConnected ? (
            <>
              Update the <strong>{changed.join(', ')}</strong> of your WhatsApp connection.
            </>
          ) : (
            <>
              Phone Number ID <strong>{input.phone_number_id}</strong> will be connected to your business. You'll
              then get a Callback URL and verify token to enter in Meta.
            </>
          )
        }
        confirmLabel={isConnected ? 'Save changes' : 'Connect'}
        pendingLabel="Checking with Meta…"
        isPending={saveConfig.isPending}
        onConfirm={handleConfirm}
      />
    </>
  )
}

/** A saved secret: never sent to the browser, so only dots are shown (display only, not a form value). */
function SavedSecret({ id, label, children }: { id: string; label: string; children?: ReactNode }) {
  return (
    <div className="flex gap-2">
      <Input
        id={id}
        value="••••••••••••••••"
        readOnly
        disabled
        aria-describedby={`${id}-saved`}
        className="tracking-widest"
      />
      <span id={`${id}-saved`} className="sr-only">
        The {label} is saved and hidden.
      </span>
      {children}
    </div>
  )
}

function DisconnectButton() {
  const deleteConfig = useDeleteWhatsAppConfiguration()
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleConfirm = () => {
    setError(null)
    deleteConfig.mutate(undefined, {
      onSuccess: () => setConfirmOpen(false),
      onError: (err) => {
        setConfirmOpen(false)
        setError(`Couldn't disconnect: ${err.message}`)
      },
    })
  }

  return (
    <>
      <div className="flex flex-col items-end gap-1">
        <Button type="button" variant="outline" onClick={() => setConfirmOpen(true)}>
          <Unplug /> Disconnect
        </Button>
        {error && (
          <p role="alert" className="text-destructive text-xs">
            {error}
          </p>
        )}
      </div>
      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title="Disconnect WhatsApp?"
        description="Your saved WhatsApp settings will be deleted, and customers' messages will no longer reach your assistant. You can connect again later (with a new verify token)."
        confirmLabel="Disconnect"
        pendingLabel="Disconnecting…"
        destructive
        isPending={deleteConfig.isPending}
        onConfirm={handleConfirm}
      />
    </>
  )
}

/** The number Meta confirmed when the details were checked: shows the owner which number is connected. */
function ConnectedNumber({ config }: { config: WhatsAppConfiguration }) {
  if (!config.display_phone_number && !config.verified_name) return null
  return (
    <div className="flex items-center gap-3 rounded-lg border px-4 py-3">
      <Phone className="text-muted-foreground size-4 shrink-0" />
      <div className="grid gap-0.5">
        <p className="text-sm font-medium">
          {[config.display_phone_number, config.verified_name].filter(Boolean).join(' · ')}
        </p>
        <p className="text-muted-foreground text-xs">Connected number, as verified by Meta</p>
      </div>
    </div>
  )
}

/** The two values the owner enters in Meta, with copy buttons and the steps. */
function WebhookSetup({ config }: { config: WhatsAppConfiguration }) {
  return (
    <section className="bg-muted/40 grid gap-4 rounded-lg border p-4" aria-labelledby="whatsapp-webhook-title">
      <div className="grid gap-1">
        <h3 id="whatsapp-webhook-title" className="text-sm font-semibold">
          Webhook setup in Meta
        </h3>
        <ol className="text-muted-foreground list-decimal space-y-0.5 pl-5 text-xs">
          <li>In your Meta app, open WhatsApp → Configuration → Webhook and click Edit.</li>
          <li>Paste the Callback URL and the Verify token below, then click Verify and save.</li>
          <li>
            Under Webhook fields, subscribe to <strong>messages</strong>.
          </li>
        </ol>
      </div>
      <CopyField id="whatsapp-webhook-url" label="Callback URL" value={config.webhook_url} />
      <CopyField id="whatsapp-verify-token" label="Verify token" value={config.verify_token} />
    </section>
  )
}

function CopyField({ id, label, value }: { id: string; label: string; value: string }) {
  const [status, setStatus] = useState<'idle' | 'copied' | 'failed'>('idle')

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value)
      setStatus('copied')
    } catch {
      setStatus('failed') // e.g. no clipboard access: the value can still be selected by hand
    }
    setTimeout(() => setStatus('idle'), 2000)
  }

  return (
    <FormField
      id={id}
      label={label}
      error={status === 'failed' ? "Couldn't copy: select the text and copy it yourself." : undefined}
    >
      <div className="flex gap-2">
        <Input id={id} value={value} readOnly className="font-mono text-xs" onFocus={(e) => e.target.select()} />
        <Button type="button" variant="outline" size="icon" onClick={copy} aria-label={`Copy ${label}`}>
          {status === 'copied' ? <Check /> : <Copy />}
        </Button>
      </div>
    </FormField>
  )
}
