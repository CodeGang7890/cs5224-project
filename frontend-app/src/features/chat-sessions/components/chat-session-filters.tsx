import { useEffect, useRef, useState } from 'react'
import { Search, X } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { NativeSelect } from '@/components/ui/native-select'

import { countActiveFilters, ORDERING_OPTIONS, type ChatFilterValues } from '../hooks/use-chat-session-params'
import type { ChatStep } from '../hooks/use-chat-steps'
import type { ChatSessionOrdering, SandboxFilter } from '../types'

interface ChatSessionFiltersProps {
  values: ChatFilterValues
  steps: ChatStep[]
  onChange: (changes: Partial<Omit<ChatFilterValues, 'page'>>) => void
  onClear: () => void
}

/** Search, filters and sorting for the Chats tab. */
export function ChatSessionFilters({ values, steps, onChange, onClear }: ChatSessionFiltersProps) {
  // Search as you type, without a request per keystroke. The box keeps its own text while you
  // type, and follows the URL when the search changes elsewhere (e.g. "Clear filters", back button).
  const [search, setSearch] = useState(values.search)
  const [urlSearch, setUrlSearch] = useState(values.search)
  if (values.search !== urlSearch) {
    setUrlSearch(values.search)
    setSearch(values.search)
  }
  const searchTimer = useRef<ReturnType<typeof setTimeout>>(undefined)
  useEffect(() => () => clearTimeout(searchTimer.current), [])

  const onSearchChange = (text: string) => {
    setSearch(text)
    clearTimeout(searchTimer.current)
    searchTimer.current = setTimeout(() => onChange({ search: text }), 300)
  }

  const activeCount = countActiveFilters(values)

  return (
    <div className="grid gap-3 rounded-xl border p-3">
      <div className="flex flex-wrap items-end gap-3">
        <div className="relative min-w-56 flex-1">
          <Search className="text-muted-foreground pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2" />
          <Input
            value={search}
            onChange={(event) => onSearchChange(event.target.value)}
            placeholder="Search name or phone number"
            aria-label="Search by name or phone number"
            className="pl-8"
          />
        </div>
        <Field label="Sort by" id="chat-ordering" className="w-44">
          <NativeSelect
            id="chat-ordering"
            value={values.ordering}
            onChange={(event) => onChange({ ordering: event.target.value as ChatSessionOrdering })}
          >
            {ORDERING_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </NativeSelect>
        </Field>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-7">
        <Field label="Chats" id="chat-sandbox">
          <NativeSelect
            id="chat-sandbox"
            value={values.sandbox}
            onChange={(event) => onChange({ sandbox: event.target.value as SandboxFilter })}
          >
            <option value="exclude">Customer chats</option>
            <option value="include">Customer + sandbox</option>
            <option value="only">Sandbox only</option>
          </NativeSelect>
        </Field>
        <Field label="Current step" id="chat-state">
          <NativeSelect id="chat-state" value={values.state} onChange={(event) => onChange({ state: event.target.value })}>
            <option value="">Any step</option>
            {steps.map((step) => (
              <option key={step.value} value={step.value}>
                {step.label}
              </option>
            ))}
          </NativeSelect>
        </Field>
        <Field label="Messages" id="chat-messages">
          <NativeSelect
            id="chat-messages"
            value={values.messages}
            onChange={(event) => onChange({ messages: event.target.value as ChatFilterValues['messages'] })}
          >
            <option value="">Any</option>
            <option value="true">Has messages</option>
            <option value="false">No messages yet</option>
          </NativeSelect>
        </Field>
        <DateField label="Last chat from" id="chat-last-from" value={values.lastFrom} max={values.lastTo} onChange={(lastFrom) => onChange({ lastFrom })} />
        <DateField label="Last chat to" id="chat-last-to" value={values.lastTo} min={values.lastFrom} onChange={(lastTo) => onChange({ lastTo })} />
        <DateField label="Started from" id="chat-created-from" value={values.createdFrom} max={values.createdTo} onChange={(createdFrom) => onChange({ createdFrom })} />
        <DateField label="Started to" id="chat-created-to" value={values.createdTo} min={values.createdFrom} onChange={(createdTo) => onChange({ createdTo })} />
      </div>

      {activeCount > 0 && (
        <div className="flex items-center justify-between gap-2 text-sm">
          <span className="text-muted-foreground">
            {activeCount} filter{activeCount === 1 ? '' : 's'} applied
          </span>
          <Button variant="ghost" size="sm" onClick={onClear}>
            <X /> Clear filters
          </Button>
        </div>
      )}
    </div>
  )
}

function Field({ label, id, className, children }: { label: string; id: string; className?: string; children: React.ReactNode }) {
  return (
    <div className={`grid gap-1.5 ${className ?? ''}`}>
      <Label htmlFor={id} className="text-muted-foreground text-xs">
        {label}
      </Label>
      {children}
    </div>
  )
}

function DateField({
  label,
  id,
  value,
  min,
  max,
  onChange,
}: {
  label: string
  id: string
  value: string
  min?: string
  max?: string
  onChange: (value: string) => void
}) {
  return (
    <Field label={label} id={id}>
      <Input
        id={id}
        type="date"
        value={value}
        min={min || undefined}
        max={max || undefined}
        onChange={(event) => onChange(event.target.value)}
      />
    </Field>
  )
}
