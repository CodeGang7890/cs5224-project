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

import { useAnswerQuestion } from '../hooks/use-questions'
import { QUESTION_LIMITS, answerMessage } from '../limits'
import type { UnansweredQuestion } from '../types'

interface AnswerQuestionDialogProps {
  /** The question to answer; undefined closes the dialog. */
  question: UnansweredQuestion | undefined
  onClose: () => void
}

/** Answer a question: it's saved as an FAQ and sent to the customer. Asks for confirmation first. */
export function AnswerQuestionDialog({ question, onClose }: AnswerQuestionDialogProps) {
  return (
    <Dialog open={question !== undefined} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[90svh] overflow-y-auto sm:max-w-xl">
        {/* Remounted on every open, so the form always starts from the customer's question. */}
        {question && <AnswerForm item={question} onDone={onClose} />}
      </DialogContent>
    </Dialog>
  )
}

function AnswerForm({ item, onDone }: { item: UnansweredQuestion; onDone: () => void }) {
  const answerQuestion = useAnswerQuestion()
  const [question, setQuestion] = useState(item.question)
  const [answer, setAnswer] = useState('')
  const [errors, setErrors] = useState<FormErrors>({ fields: {} })
  const [confirmOpen, setConfirmOpen] = useState(false)
  const cleanQuestion = question.trim().replace(/\s+/g, ' ')
  const cleanAnswer = answer.trim()

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const fields: Record<string, string> = {}
    if (!cleanQuestion) fields.question = 'The question is required.'
    else if (cleanQuestion.length > QUESTION_LIMITS.questionMaxLength) {
      fields.question = `Must be at most ${QUESTION_LIMITS.questionMaxLength} characters.`
    }
    if (!cleanAnswer) fields.answer = 'Write an answer.'
    else if (cleanAnswer.length > QUESTION_LIMITS.answerMaxLength) {
      fields.answer = `Must be at most ${QUESTION_LIMITS.answerMaxLength.toLocaleString()} characters.`
    }
    setErrors({ fields })
    if (Object.keys(fields).length === 0) setConfirmOpen(true)
  }

  const handleConfirm = () => {
    const input = cleanQuestion === item.question ? { answer: cleanAnswer } : { answer: cleanAnswer, question: cleanQuestion }
    answerQuestion.mutate(
      { id: item.id, input },
      {
        onSuccess: () => {
          setConfirmOpen(false)
          onDone()
        },
        onError: (error) => {
          setConfirmOpen(false)
          const formErrors = getFormErrors(error)
          // `status`: the question was answered or dismissed meanwhile (e.g. in another tab).
          setErrors({ fields: formErrors.fields, form: formErrors.form ?? formErrors.fields.status })
        },
      },
    )
  }

  const customer = item.display_name || item.phone_number || 'the customer'

  return (
    <>
      <form onSubmit={handleSubmit} noValidate className="grid gap-5">
        <DialogHeader>
          <DialogTitle>Answer question</DialogTitle>
          <DialogDescription>
            Asked by {customer} on {new Date(item.created_time).toLocaleString()}. Your answer is sent to them in
            the chat and saved to your FAQs, so the assistant can answer it next time.
          </DialogDescription>
        </DialogHeader>

        <FormField
          id="question-text"
          label="Question"
          required
          error={errors.fields.question || undefined}
          hint="You can tidy up the wording: this is how it appears in your FAQs."
          length={{ current: cleanQuestion.length, max: QUESTION_LIMITS.questionMaxLength }}
        >
          <Input
            id="question-text"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            aria-invalid={errors.fields.question ? true : undefined}
          />
        </FormField>

        <FormField
          id="question-answer"
          label="Answer"
          required
          error={errors.fields.answer || undefined}
          length={{ current: cleanAnswer.length, max: QUESTION_LIMITS.answerMaxLength }}
        >
          <Textarea
            id="question-answer"
            value={answer}
            onChange={(e) => setAnswer(e.target.value)}
            aria-invalid={errors.fields.answer ? true : undefined}
            className="min-h-28 max-h-64"
            autoFocus
          />
        </FormField>

        <div className="grid gap-1 rounded-md border bg-muted/40 p-3 text-sm">
          <span className="text-muted-foreground text-xs">{customer} will receive:</span>
          <p className="whitespace-pre-wrap break-words">
            {answerMessage(cleanQuestion || item.question, cleanAnswer || '…')}
          </p>
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
          <Button type="submit">Send answer</Button>
        </DialogFooter>
      </form>

      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title="Send this answer?"
        description={
          <>
            The answer will be sent to {customer} in the chat and added to your FAQs (you can edit it later in the
            FAQ tab).
          </>
        }
        confirmLabel="Send answer"
        pendingLabel="Sending…"
        isPending={answerQuestion.isPending}
        onConfirm={handleConfirm}
      />
    </>
  )
}
