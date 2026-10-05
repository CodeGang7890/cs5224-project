import { blockDetailFields } from '../details'
import { DETAILS_COLLECTION_BLOCK } from '../types'
import { useChatConfiguration } from './use-chat-configuration'

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
