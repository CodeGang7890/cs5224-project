import { CHAT_STEP_LABELS, CHAT_STEPS } from '@/features/workflow'

import type { ChatSession } from '../types'

export interface ChatStepOption {
  /** The step as a query-string value (what `chat_state_id` expects). */
  value: string
  label: string
}

const STEP_OPTIONS: ChatStepOption[] = CHAT_STEPS.map((step) => ({ value: step, label: CHAT_STEP_LABELS[step] }))

/** The chat flow's (fixed) steps as "current step" options and labels. */
export function useChatSteps() {
  /** Label of a session's current step (the raw value if it's unknown). */
  const stepLabel = (step: ChatSession['chat_state_id']): string => CHAT_STEP_LABELS[step] ?? step
  return { steps: STEP_OPTIONS, stepLabel }
}
