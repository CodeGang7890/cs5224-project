import { useState, type FormEvent } from 'react'

import { FormField } from '@/components/common/form-field'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Textarea } from '@/components/ui/textarea'

import { DEFAULT_SEND_MESSAGE, SEND_MESSAGE_MAX_LENGTH } from '../blocks'

interface SendMessageDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** The block's current message. */
  message: string | undefined
  onApply: (message: string) => void
}

/**
 * Edits the message a Send message block sends. Applying only changes the editor; the workflow's
 * Save button saves it to the backend.
 */
export function SendMessageDialog({ open, onOpenChange, message, onApply }: SendMessageDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Message to send</DialogTitle>
          <DialogDescription>
            When the chat reaches this block, the customer gets exactly this message, and the chat moves straight on to
            the next block.
          </DialogDescription>
        </DialogHeader>
        {/* Remounted on each open, so it always starts from the block's current message. */}
        {open && (
          <SendMessageForm
            initial={message ?? DEFAULT_SEND_MESSAGE}
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

function SendMessageForm({
  initial,
  onCancel,
  onApply,
}: {
  initial: string
  onCancel: () => void
  onApply: (message: string) => void
}) {
  const [message, setMessage] = useState(initial)
  const [submitted, setSubmitted] = useState(false)
  const error = !message.trim()
    ? 'Enter a message.'
    : message.length > SEND_MESSAGE_MAX_LENGTH
      ? `At most ${SEND_MESSAGE_MAX_LENGTH.toLocaleString()} characters.`
      : undefined

  const onSubmit = (event: FormEvent) => {
    event.preventDefault()
    setSubmitted(true)
    if (!error) onApply(message.trim())
  }

  return (
    <form onSubmit={onSubmit} className="grid gap-4" noValidate>
      <FormField
        id="send-message-text"
        label="Message"
        error={submitted ? error : undefined}
        hint="Sent as it is, like a WhatsApp message. Line breaks are kept."
        length={{ current: message.length, max: SEND_MESSAGE_MAX_LENGTH }}
      >
        <Textarea
          id="send-message-text"
          value={message}
          onChange={(event) => setMessage(event.target.value)}
          rows={5}
          autoFocus
          aria-invalid={(submitted && error !== undefined) || undefined}
        />
      </FormField>
      <DialogFooter className="items-center sm:justify-between">
        <p className="text-muted-foreground text-xs">Save the workflow afterwards to keep the change.</p>
        <div className="flex gap-2">
          <Button type="button" variant="outline" onClick={onCancel}>
            Cancel
          </Button>
          <Button type="submit">Apply</Button>
        </div>
      </DialogFooter>
    </form>
  )
}
