import type { Faq, FaqInput } from './types'

// Mirrors configuration-service product_app/models.py. The backend validates too.
export const FAQ_LIMITS = {
  questionMaxLength: 300,
  answerMaxLength: 10_000,
} as const

export const FAQ_FIELD_LABELS: Record<keyof FaqInput, string> = {
  question: 'Question',
  answer: 'Answer',
}

export const emptyFaqValues: FaqInput = { question: '', answer: '' }

export function normaliseFaqInput(values: FaqInput): FaqInput {
  return { question: values.question.trim(), answer: values.answer.trim() }
}

export function validateFaq(values: FaqInput): Partial<Record<keyof FaqInput, string>> {
  const { question, answer } = normaliseFaqInput(values)
  const errors: Partial<Record<keyof FaqInput, string>> = {}
  if (!question) errors.question = 'Question is required.'
  else if (question.length > FAQ_LIMITS.questionMaxLength) {
    errors.question = `Must be at most ${FAQ_LIMITS.questionMaxLength} characters.`
  }
  if (!answer) errors.answer = 'Answer is required.'
  else if (answer.length > FAQ_LIMITS.answerMaxLength) {
    errors.answer = `Must be at most ${FAQ_LIMITS.answerMaxLength.toLocaleString()} characters.`
  }
  return errors
}

/** Only the fields that differ from the saved FAQ (for PATCH). */
export function changedFaqFields(original: Faq, input: FaqInput): Partial<FaqInput> {
  const changes: Partial<FaqInput> = {}
  if (original.question !== input.question) changes.question = input.question
  if (original.answer !== input.answer) changes.answer = input.answer
  return changes
}
