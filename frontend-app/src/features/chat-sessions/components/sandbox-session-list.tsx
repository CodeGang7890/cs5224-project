import { Loader2, MessageSquare } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

import { useIsSendingSandboxMessage } from '../hooks/use-chat-sessions'
import { sessionLabel } from '../sandbox'
import type { ChatSession } from '../types'

function formatLastChat(iso: string) {
  const date = new Date(iso)
  const today = new Date().toDateString() === date.toDateString()
  return today
    ? date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    : date.toLocaleDateString([], { day: 'numeric', month: 'short' })
}

interface SandboxSessionListProps {
  sessions: ChatSession[]
  selectedId: number | undefined
  onSelect: (id: number) => void
  hasMore: boolean
  isLoadingMore: boolean
  onLoadMore: () => void
}

/** The sandbox chats, most recent first. */
export function SandboxSessionList({
  sessions,
  selectedId,
  onSelect,
  hasMore,
  isLoadingMore,
  onLoadMore,
}: SandboxSessionListProps) {
  return (
    <div className="flex-1 overflow-y-auto">
      <ul className="grid gap-0.5 p-2">
        {sessions.map((session) => (
          <SessionItem
            key={session.id}
            session={session}
            selected={session.id === selectedId}
            onSelect={() => onSelect(session.id)}
          />
        ))}
      </ul>
      {hasMore && (
        <div className="px-2 pb-2">
          <Button variant="ghost" size="sm" className="w-full" disabled={isLoadingMore} onClick={onLoadMore}>
            {isLoadingMore ? 'Loading…' : 'Load more'}
          </Button>
        </div>
      )}
    </div>
  )
}

function SessionItem({ session, selected, onSelect }: { session: ChatSession; selected: boolean; onSelect: () => void }) {
  const isSending = useIsSendingSandboxMessage(session.id)
  const lastMessage = session.chat_message_json.at(-1)

  return (
    <li>
      <button
        type="button"
        onClick={onSelect}
        aria-current={selected || undefined}
        className={cn(
          'flex w-full items-start gap-3 rounded-lg px-3 py-2.5 text-left transition-colors',
          selected ? 'bg-accent' : 'hover:bg-accent/50',
        )}
      >
        <div className="bg-muted text-muted-foreground mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-full">
          <MessageSquare className="size-4" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-baseline justify-between gap-2">
            <p className="truncate text-sm font-medium">{sessionLabel(session)}</p>
            <span className="text-muted-foreground shrink-0 text-[11px]">{formatLastChat(session.last_chat_time)}</span>
          </div>
          <p className="text-muted-foreground flex items-center gap-1 truncate text-xs">
            {isSending ? (
              <>
                <Loader2 className="size-3 animate-spin" /> Waiting for reply…
              </>
            ) : lastMessage ? (
              `${lastMessage.sent_by === 'customer' ? 'You: ' : ''}${lastMessage.message}`
            ) : (
              'No messages yet'
            )}
          </p>
        </div>
      </button>
    </li>
  )
}
