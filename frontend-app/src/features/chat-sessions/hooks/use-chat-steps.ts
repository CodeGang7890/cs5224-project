import { BLOCK_META, blockDetailFields, DETAILS_COLLECTION_BLOCK, useChatConfiguration } from '@/features/workflow'

import type { ChatSession } from '../types'

export interface ChatStep {
  /** The block id as a query-string value (what `chat_state_id` expects). */
  value: string
  label: string
}

/**
 * The business's workflow blocks as "current step" options and labels. When a block type is
 * used more than once, later ones are numbered ("Confirmation 2").
 */
export function useChatSteps() {
  const { data } = useChatConfiguration()
  const blocks = data?.config_json ?? []

  const seen: Record<string, number> = {}
  const steps: ChatStep[] = blocks.map((block) => {
    const count = (seen[block.block_type] = (seen[block.block_type] ?? 0) + 1)
    const label = BLOCK_META[block.block_type].label
    return { value: String(block.id), label: count > 1 ? `${label} ${count}` : label }
  })

  /** Label of a session's current step; `null` if it isn't at a block (or the block was removed). */
  const stepLabel = (stateId: ChatSession['chat_state_id']): string | null => {
    if (stateId === null) return null
    const index = blocks.findIndex((block) => block.id === stateId)
    return index === -1 ? `Removed step (${stateId})` : steps[index].label
  }

  return { steps, stepLabel }
}

/** Detail field key → label, from the workflow's Details collection blocks (like the backend's `detail_labels`). */
export function useDetailLabels(): Record<string, string> {
  const { data } = useChatConfiguration()
  const labels: Record<string, string> = {}
  for (const block of data?.config_json ?? []) {
    if (block.block_type !== DETAILS_COLLECTION_BLOCK) continue
    for (const field of blockDetailFields(block.fields)) labels[field.key] = field.label
  }
  return labels
}
