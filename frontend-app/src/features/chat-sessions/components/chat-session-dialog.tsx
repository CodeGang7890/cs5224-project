import { Badge } from '@/components/ui/badge'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'

import type { ChatSession } from '../types'
import { ChatMessageBubble } from './chat-message-bubble'
import { ChatStateSummary } from './chat-state-summary'

interface ChatSessionDialogProps {
  session: ChatSession | undefined
  stepLabel: (stateId: ChatSession['chat_state_id']) => string | null
  onClose: () => void
}

/** Read-only view of one chat: details and the whole conversation. */
export function ChatSessionDialog({ session, stepLabel, onClose }: ChatSessionDialogProps) {
  return (
    <Dialog open={session !== undefined} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="flex max-h-[85svh] flex-col gap-4 sm:max-w-2xl">
        {session && (
          <>
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                {session.display_name || 'Unnamed customer'}
                {session.is_sandbox && (
                  <Badge variant="outline" className="border-amber-500/50 text-amber-700 dark:text-amber-400">
                    Sandbox
                  </Badge>
                )}
              </DialogTitle>
              <DialogDescription>{session.phone_number || 'No phone number'} · read only</DialogDescription>
            </DialogHeader>

            <dl className="grid grid-cols-2 gap-x-4 gap-y-2 rounded-lg border p-3 text-sm sm:grid-cols-4">
              <Detail label="Current step" value={stepLabel(session.chat_state_id) ?? '—'} />
              <Detail label="Messages" value={String(session.chat_message_json.length)} />
              <Detail label="Started" value={new Date(session.created_time).toLocaleString()} />
              <Detail label="Last chat" value={new Date(session.last_chat_time).toLocaleString()} />
            </dl>

            <ChatStateSummary data={session.chat_state_data} className="rounded-lg border px-3 py-2 text-sm" />

            <div className="bg-muted/20 min-h-0 flex-1 overflow-y-auto rounded-lg border p-4">
              {session.chat_message_json.length === 0 ? (
                <p className="text-muted-foreground py-8 text-center text-sm">No messages yet.</p>
              ) : (
                <ul className="flex flex-col gap-3">
                  {session.chat_message_json.map((message, index) => (
                    <ChatMessageBubble key={`${index}-${message.message_time}`} message={message} perspective="business" />
                  ))}
                </ul>
              )}
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid gap-0.5">
      <dt className="text-muted-foreground text-xs">{label}</dt>
      <dd className="font-medium">{value}</dd>
    </div>
  )
}
