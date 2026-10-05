import { useSearchParams } from 'react-router'

import type { ChatSessionListParams, ChatSessionOrdering, SandboxFilter } from '../types'

// The Chats tab keeps every filter in the URL, so a filtered view can be refreshed, shared or
// reached with the back button. Dates are kept as YYYY-MM-DD and sent as local-day ISO bounds.

export const PAGE_SIZES = [10, 20, 50, 100] as const
export const DEFAULT_PAGE_SIZE = 20
export const DEFAULT_ORDERING: ChatSessionOrdering = '-last_chat_time'
export const DEFAULT_SANDBOX: SandboxFilter = 'exclude'

export const ORDERING_OPTIONS: { value: ChatSessionOrdering; label: string }[] = [
  { value: '-last_chat_time', label: 'Most recent chat' },
  { value: 'last_chat_time', label: 'Oldest chat' },
  { value: '-created_time', label: 'Newest started' },
  { value: 'created_time', label: 'Oldest started' },
  { value: 'display_name', label: 'Name (A–Z)' },
  { value: '-display_name', label: 'Name (Z–A)' },
  { value: 'phone_number', label: 'Phone number' },
]

const SANDBOX_VALUES: SandboxFilter[] = ['exclude', 'include', 'only']

/** URL search params of the Chats tab (all optional). */
export interface ChatFilterValues {
  search: string
  state: string
  messages: '' | 'true' | 'false'
  sandbox: SandboxFilter
  lastFrom: string
  lastTo: string
  createdFrom: string
  createdTo: string
  ordering: ChatSessionOrdering
  page: number
  pageSize: number
}

const PARAM_NAMES: Record<Exclude<keyof ChatFilterValues, 'page' | 'pageSize'>, string> = {
  search: 'search',
  state: 'state',
  messages: 'messages',
  sandbox: 'sandbox',
  lastFrom: 'last_from',
  lastTo: 'last_to',
  createdFrom: 'created_from',
  createdTo: 'created_to',
  ordering: 'ordering',
}

const DATE = /^\d{4}-\d{2}-\d{2}$/

function readDate(params: URLSearchParams, name: string) {
  const value = params.get(name) ?? ''
  return DATE.test(value) ? value : ''
}

function readValues(params: URLSearchParams): ChatFilterValues {
  const ordering = params.get('ordering') as ChatSessionOrdering
  const sandbox = params.get('sandbox') as SandboxFilter
  const messages = params.get('messages')
  const page = Number(params.get('page'))
  const pageSize = Number(params.get('page_size'))
  return {
    search: params.get('search') ?? '',
    state: params.get('state') ?? '',
    messages: messages === 'true' || messages === 'false' ? messages : '',
    sandbox: SANDBOX_VALUES.includes(sandbox) ? sandbox : DEFAULT_SANDBOX,
    lastFrom: readDate(params, 'last_from'),
    lastTo: readDate(params, 'last_to'),
    createdFrom: readDate(params, 'created_from'),
    createdTo: readDate(params, 'created_to'),
    ordering: ORDERING_OPTIONS.some((o) => o.value === ordering) ? ordering : DEFAULT_ORDERING,
    page: Number.isInteger(page) && page > 0 ? page : 1,
    pageSize: (PAGE_SIZES as readonly number[]).includes(pageSize) ? pageSize : DEFAULT_PAGE_SIZE,
  }
}

const startOfDay = (date: string) => new Date(`${date}T00:00:00`).toISOString()
const endOfDay = (date: string) => new Date(`${date}T23:59:59.999`).toISOString()

/** Converts the URL values to API query parameters (empty filters are left out). */
export function toListParams(values: ChatFilterValues): ChatSessionListParams {
  return {
    page: values.page,
    page_size: values.pageSize,
    ordering: values.ordering,
    sandbox: values.sandbox,
    search: values.search.trim() || undefined,
    chat_state_id: values.state || undefined,
    has_messages: values.messages || undefined,
    last_chat_time_after: values.lastFrom ? startOfDay(values.lastFrom) : undefined,
    last_chat_time_before: values.lastTo ? endOfDay(values.lastTo) : undefined,
    created_time_after: values.createdFrom ? startOfDay(values.createdFrom) : undefined,
    created_time_before: values.createdTo ? endOfDay(values.createdTo) : undefined,
  }
}

/** Filters that narrow the list (not sorting / paging / the default sandbox setting). */
export function countActiveFilters(values: ChatFilterValues): number {
  return [
    values.search.trim(),
    values.state,
    values.messages,
    values.sandbox !== DEFAULT_SANDBOX,
    values.lastFrom,
    values.lastTo,
    values.createdFrom,
    values.createdTo,
  ].filter(Boolean).length
}

/** Filter, sort and paging state of the Chats tab, stored in the URL. */
export function useChatSessionParams() {
  const [searchParams, setSearchParams] = useSearchParams()
  const values = readValues(searchParams)

  /** Changes filters/sorting; goes back to page 1, since the old page may no longer exist. */
  const setFilters = (changes: Partial<Omit<ChatFilterValues, 'page'>>) =>
    setSearchParams(
      (params) => {
        for (const [key, value] of Object.entries(changes)) {
          if (key === 'pageSize') {
            if (value === DEFAULT_PAGE_SIZE) params.delete('page_size')
            else params.set('page_size', String(value))
            continue
          }
          const name = PARAM_NAMES[key as keyof typeof PARAM_NAMES]
          const isDefault =
            value === '' || (key === 'sandbox' && value === DEFAULT_SANDBOX) || (key === 'ordering' && value === DEFAULT_ORDERING)
          if (isDefault) params.delete(name)
          else params.set(name, String(value))
        }
        params.delete('page')
        return params
      },
      { replace: true },
    )

  const setPage = (page: number) =>
    setSearchParams(
      (params) => {
        if (page <= 1) params.delete('page')
        else params.set('page', String(page))
        return params
      },
      { replace: true },
    )

  /** Clears every filter, keeping sorting and page size. */
  const clearFilters = () =>
    setFilters({
      search: '',
      state: '',
      messages: '',
      sandbox: DEFAULT_SANDBOX,
      lastFrom: '',
      lastTo: '',
      createdFrom: '',
      createdTo: '',
    })

  const openChatId = Number(searchParams.get('chat')) || null
  const setOpenChat = (id: number | null) =>
    setSearchParams(
      (params) => {
        if (id === null) params.delete('chat')
        else params.set('chat', String(id))
        return params
      },
      { replace: true },
    )

  return { values, setFilters, setPage, clearFilters, openChatId, setOpenChat }
}
