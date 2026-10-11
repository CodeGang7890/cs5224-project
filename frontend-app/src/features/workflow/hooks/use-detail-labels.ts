import { DEFAULT_DETAIL_FIELDS } from '../details'
import { useChatConfiguration } from './use-chat-configuration'

/** Which details list: product orders (Details collection) or service bookings (Booking details). */
export type DetailsKind = 'order' | 'booking'

/** Detail field key → label, from that list's fields (like the backend's `detail_labels`). */
export function useDetailLabels(kind: DetailsKind): Record<string, string> {
  const { data } = useChatConfiguration()
  const fields = (kind === 'booking' ? data?.schedule_detail_fields : data?.product_detail_fields) ?? DEFAULT_DETAIL_FIELDS
  return Object.fromEntries(fields.map((field) => [field.key, field.label]))
}
