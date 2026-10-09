import { DEFAULT_DETAIL_FIELDS } from '../details'
import { useChatConfiguration } from './use-chat-configuration'

/** Detail field key → label, from the Details collection step's fields (like the backend's `detail_labels`). */
export function useDetailLabels(): Record<string, string> {
  const { data } = useChatConfiguration()
  const fields = data?.detail_fields ?? DEFAULT_DETAIL_FIELDS
  return Object.fromEntries(fields.map((field) => [field.key, field.label]))
}
