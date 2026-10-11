import { useState, type FormEvent } from 'react'
import { CircleAlert } from 'lucide-react'

import { FormField } from '@/components/common/form-field'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Skeleton } from '@/components/ui/skeleton'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { useCurrentUser } from '@/features/auth'
import { cn } from '@/lib/utils'

import { useReplyStyles } from '../hooks/use-chat-configuration'
import {
  BUSINESS_NAME_PLACEHOLDER,
  SETTINGS_LIMITS,
  type ChatSettings,
  normalizeSettings,
  validateSettings,
  welcomePreview,
} from '../settings'

interface ChatSettingsDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** The editor's current (maybe unsaved) settings. */
  settings: ChatSettings
  /** Updates the editor; the workflow's Save persists it. */
  onApply: (settings: ChatSettings) => void
}

/** The Welcome & style block's dialog: the welcome message, and the style the assistant writes in. */
export function ChatSettingsDialog({ open, onOpenChange, settings, onApply }: ChatSettingsDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[85svh] flex-col gap-4 sm:max-w-2xl">
        {/* Remounted on every open, so it starts from the editor's current settings. */}
        {open && (
          <SettingsForm
            settings={settings}
            onCancel={() => onOpenChange(false)}
            onApply={(next) => {
              onApply(next)
              onOpenChange(false)
            }}
          />
        )}
      </DialogContent>
    </Dialog>
  )
}

function SettingsForm({
  settings,
  onCancel,
  onApply,
}: {
  settings: ChatSettings
  onCancel: () => void
  onApply: (settings: ChatSettings) => void
}) {
  const styles = useReplyStyles()
  const { data: user } = useCurrentUser()
  const [welcomeOn, setWelcomeOn] = useState(settings.welcome_message.trim() !== '')
  const [values, setValues] = useState<ChatSettings>(settings)
  const [errors, setErrors] = useState<Partial<Record<keyof ChatSettings, string>>>({})

  const set = <K extends keyof ChatSettings>(key: K, value: ChatSettings[K]) => {
    setValues((current) => ({ ...current, [key]: value }))
    setErrors((current) => ({ ...current, [key]: undefined }))
  }
  // Switched off: no welcome message (the text is cleared when applied).
  const result: ChatSettings = { ...values, welcome_message: welcomeOn ? values.welcome_message : '' }
  const preview = welcomePreview(values.welcome_message, user?.business_name ?? 'your business')

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const found = validateSettings(result)
    if (welcomeOn && !values.welcome_message.trim()) found.welcome_message = 'Write the welcome message, or switch it off.'
    setErrors(found)
    if (Object.keys(found).length === 0) onApply(normalizeSettings(result))
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="flex min-h-0 flex-col gap-4">
      <DialogHeader>
        <DialogTitle>Welcome & style</DialogTitle>
        <DialogDescription>
          The first thing customers see, and how the assistant writes every reply. Apply, then save the workflow.
        </DialogDescription>
      </DialogHeader>

      <div className="grid min-h-0 gap-5 overflow-y-auto pr-1">
        <section className="grid gap-3" aria-labelledby="welcome-heading">
          <div className="flex items-start justify-between gap-4">
            <div className="grid gap-1">
              <h3 id="welcome-heading" className="text-sm font-semibold">
                Welcome message
              </h3>
              <p className="text-muted-foreground text-xs">
                Sent word for word as the reply to a customer's very first message. If they only said hello, that's the
                whole reply; if they already asked for something, the assistant's reply follows it.
              </p>
            </div>
            <Switch checked={welcomeOn} onCheckedChange={setWelcomeOn} aria-label="Send a welcome message" />
          </div>
          {welcomeOn && (
            <>
              <FormField
                id="welcome-message"
                label="Message"
                error={errors.welcome_message}
                length={{ current: values.welcome_message.trim().length, max: SETTINGS_LIMITS.welcomeMessageMaxLength }}
                hint={
                  <>
                    You can use <code>{BUSINESS_NAME_PLACEHOLDER}</code> for your business's name.
                  </>
                }
              >
                <Textarea
                  id="welcome-message"
                  rows={4}
                  value={values.welcome_message}
                  placeholder={`Hi, welcome to ${BUSINESS_NAME_PLACEHOLDER}! I can help you order, book or answer questions.`}
                  onChange={(event) => set('welcome_message', event.target.value)}
                />
              </FormField>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="justify-self-start"
                onClick={() => set('welcome_message', `${values.welcome_message}${BUSINESS_NAME_PLACEHOLDER}`)}
              >
                Insert {BUSINESS_NAME_PLACEHOLDER}
              </Button>
              {preview && (
                <div className="grid gap-1">
                  <p className="text-muted-foreground text-xs">What the customer sees</p>
                  <p className="bg-muted max-w-md rounded-2xl rounded-tl-sm px-3 py-2 text-sm whitespace-pre-wrap">{preview}</p>
                </div>
              )}
            </>
          )}
        </section>

        <section className="grid gap-3" aria-labelledby="style-heading">
          <div className="grid gap-1">
            <h3 id="style-heading" className="text-sm font-semibold">
              Reply style
            </h3>
            <p className="text-muted-foreground text-xs">
              How the assistant writes. It only changes the tone: the assistant still never makes things up or confirms
              anything itself. Fixed messages (order summaries, confirmations, free times) stay as they are.
            </p>
          </div>
          {styles.isPending ? (
            <Skeleton className="h-40 w-full" />
          ) : styles.isError ? (
            <p role="alert" className="text-destructive text-sm">
              Couldn't load the styles: {styles.error.message}
            </p>
          ) : (
            <div role="radiogroup" aria-label="Reply style" className="grid gap-2 sm:grid-cols-2">
              {styles.data.map((style) => (
                <button
                  key={style.key}
                  type="button"
                  role="radio"
                  aria-checked={values.reply_style === style.key}
                  onClick={() => set('reply_style', style.key)}
                  className={cn(
                    'grid gap-0.5 rounded-lg border p-3 text-left transition-colors',
                    values.reply_style === style.key ? 'border-primary ring-primary bg-primary/5 ring-1' : 'hover:bg-muted/50',
                  )}
                >
                  <span className="text-sm font-medium">{style.label}</span>
                  <span className="text-muted-foreground text-xs">{style.description}</span>
                </button>
              ))}
            </div>
          )}
          {values.reply_style === 'custom' && (
            <FormField
              id="custom-style"
              label="Your style"
              required
              error={errors.custom_style}
              length={{ current: values.custom_style.trim().length, max: SETTINGS_LIMITS.customStyleMaxLength }}
              hint={'For example: "Cheerful and short, use the customer\'s name, and sign off with Cheers!"'}
            >
              <Textarea
                id="custom-style"
                rows={3}
                value={values.custom_style}
                onChange={(event) => set('custom_style', event.target.value)}
              />
            </FormField>
          )}
        </section>
      </div>

      {Object.values(errors).some(Boolean) && (
        <p role="alert" className="text-destructive flex items-center gap-2 text-sm">
          <CircleAlert className="size-4 shrink-0" /> Fix the problems above to apply.
        </p>
      )}

      <DialogFooter>
        <Button type="button" variant="outline" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit">Apply</Button>
      </DialogFooter>
    </form>
  )
}
