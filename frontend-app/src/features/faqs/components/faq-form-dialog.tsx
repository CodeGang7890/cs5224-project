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
import { Textarea } from '@/components/ui/textarea'
import { type FormErrors, getFormErrors } from '@/lib/form-errors'

import { useSaveFaq } from '../hooks/use-faqs'
import type { Faq, FaqInput } from '../types'
import {
  FAQ_FIELD_LABELS,
  FAQ_LIMITS,
  changedFaqFields,
  emptyFaqValues,
  normaliseFaqInput,
  validateFaq,
} from '../validation'

interface FaqFormDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** The FAQ to edit; omit to create a new one. */
  faq?: Faq
}

/** Create/edit form in a dialog. Saving asks for confirmation first. */
export function FaqFormDialog({ open, onOpenChange, faq }: FaqFormDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90svh] overflow-y-auto sm:max-w-2xl">
        {/* Remounted on every open, so the form always starts from the saved values. */}
        {open && <FaqForm faq={faq} onDone={() => onOpenChange(false)} />}
      </DialogContent>
    </Dialog>
  )
}

function FaqForm({ faq, onDone }: { faq?: Faq; onDone: () => void }) {
  const isEdit = faq !== undefined
  const saveFaq = useSaveFaq()
  const [values, setValues] = useState<FaqInput>(
    faq ? { question: faq.question, answer: faq.answer } : emptyFaqValues,
  )
  const [errors, setErrors] = useState<FormErrors>({ fields: {} })
  const [confirmOpen, setConfirmOpen] = useState(false)

  const input = normaliseFaqInput(values)
  const changes = isEdit ? changedFaqFields(faq, input) : input
  const changedLabels = Object.keys(changes).map((key) => FAQ_FIELD_LABELS[key as keyof FaqInput])
  const hasChanges = changedLabels.length > 0

  const set = (key: keyof FaqInput, value: string) => {
    setValues((current) => ({ ...current, [key]: value }))
    setErrors((current) => ({ ...current, fields: { ...current.fields, [key]: '' } }))
  }

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const fieldErrors = validateFaq(values)
    setErrors({ fields: fieldErrors as Record<string, string> })
    if (Object.keys(fieldErrors).length === 0 && hasChanges) setConfirmOpen(true)
  }

  const handleConfirm = () => {
    saveFaq.mutate(isEdit ? { id: faq.id, input: changes } : { input }, {
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

  const fieldError = (key: keyof FaqInput) => errors.fields[key] || undefined

  return (
    <>
      <form onSubmit={handleSubmit} noValidate className="grid gap-5">
        <DialogHeader>
          <DialogTitle>{isEdit ? 'Edit FAQ' : 'Add FAQ'}</DialogTitle>
          <DialogDescription>
            {isEdit ? 'Update this question and its answer.' : 'Add a question your customers often ask.'}
          </DialogDescription>
        </DialogHeader>

        <FormField
          id="faq-question"
          label="Question"
          required
          error={fieldError('question')}
          length={{ current: values.question.trim().length, max: FAQ_LIMITS.questionMaxLength }}
        >
          <Input
            id="faq-question"
            value={values.question}
            onChange={(e) => set('question', e.target.value)}
            aria-invalid={fieldError('question') ? true : undefined}
            autoFocus
          />
        </FormField>

        <FormField
          id="faq-answer"
          label="Answer"
          required
          error={fieldError('answer')}
          length={{ current: values.answer.trim().length, max: FAQ_LIMITS.answerMaxLength }}
        >
          <Textarea
            id="faq-answer"
            value={values.answer}
            onChange={(e) => set('answer', e.target.value)}
            aria-invalid={fieldError('answer') ? true : undefined}
            className="min-h-40 max-h-96"
          />
        </FormField>

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
            {isEdit ? 'Save changes' : 'Add FAQ'}
          </Button>
        </DialogFooter>
      </form>

      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title={isEdit ? 'Save changes?' : 'Add this FAQ?'}
        description={
          isEdit ? (
            <>
              Update the <strong>{changedLabels.join(' and ').toLowerCase()}</strong> of this FAQ.
            </>
          ) : (
            <>“{input.question}” will be added to your FAQs.</>
          )
        }
        confirmLabel={isEdit ? 'Save changes' : 'Add FAQ'}
        pendingLabel="Saving…"
        isPending={saveFaq.isPending}
        onConfirm={handleConfirm}
      />
    </>
  )
}
