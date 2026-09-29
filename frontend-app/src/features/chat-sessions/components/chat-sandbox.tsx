import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import { CircleAlert, FlaskConical, MessageSquareDashed, RefreshCw, SendHorizontal, Workflow } from 'lucide-react'
import { Link } from 'react-router'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Textarea } from '@/components/ui/textarea'
import { paths } from '@/config/navigation'
import { useCurrentUser } from '@/features/auth'
import { getFormErrors } from '@/lib/form-errors'
import type { ApiError } from '@/types/api'

import { useSandboxSession, useSendSandboxMessage } from '../hooks/use-chat-sessions'
import {
  CHAT_MESSAGE_MAX_LENGTH,
  isMissingChatConfiguration,
  SANDBOX_DISPLAY_NAME,
  SANDBOX_PHONE_NUMBER,
} from '../sandbox'
import { ChatMessageBubble, TypingBubble } from './chat-message-bubble'

const SUGGESTIONS = ['Hi! What do you sell?', 'Are you open today?', "I'd like to place an order."]

const panelClassName = 'flex h-[calc(100svh-16rem)] min-h-[480px] flex-col overflow-hidden rounded-xl border'

/** Chat with your business's assistant as a pretend customer. Needs a logged-in business user. */
export function ChatSandbox() {
  const { data: user, isPending, error, refetch } = useCurrentUser()

  if (isPending) return <Skeleton className={panelClassName} />
  if (error) return <ErrorPanel message={`Couldn't load your account: ${error.message}`} onRetry={refetch} />
  if (user.business === null) {
    return <ErrorPanel message="Your account isn't linked to a business, so there's no assistant to chat with." />
  }
  return <SandboxChat businessId={user.business} businessName={user.business_name ?? 'your business'} />
}

function SandboxChat({ businessId, businessName }: { businessId: number; businessName: string }) {
  const session = useSandboxSession(businessId)
  const send = useSendSandboxMessage(businessId)
  const [draft, setDraft] = useState('')
  const endRef = useRef<HTMLDivElement>(null)

  const messages = session.data?.chat_message_json ?? []

  // Keep the newest message (or the typing indicator) in view.
  useEffect(() => {
    endRef.current?.scrollIntoView({ block: 'end' })
  }, [messages.length, send.isPending])

  if (session.isPending) {
    return (
      <div className={`${panelClassName} gap-3 p-4`} aria-busy="true" aria-label="Loading sandbox chat">
        <Skeleton className="h-10 w-56" />
        <Skeleton className="ml-auto h-12 w-2/5" />
        <Skeleton className="h-16 w-1/2" />
        <Skeleton className="mt-auto h-16 w-full" />
      </div>
    )
  }

  if (session.isError && !session.data) {
    if (isMissingChatConfiguration(session.error)) {
      return (
        <div className={`${panelClassName} items-center justify-center gap-3 p-6 text-center`}>
          <Workflow className="text-muted-foreground size-10" />
          <p className="font-medium">Set up your workflow first</p>
          <p className="text-muted-foreground max-w-sm text-sm">
            Chats start at your workflow's Start block, and {businessName} doesn't have a workflow yet.
          </p>
          <Button asChild>
            <Link to={paths.workflow}>Go to Workflow</Link>
          </Button>
        </div>
      )
    }
    return <ErrorPanel message={`Couldn't start the sandbox chat: ${session.error.message}`} onRetry={session.refetch} />
  }

  const sendMessage = (text: string) => {
    const message = text.trim()
    if (!message || send.isPending) return
    setDraft('')
    send.mutate(message)
  }

  const onSubmit = (event: FormEvent) => {
    event.preventDefault()
    sendMessage(draft)
  }

  // Enter sends; Shift+Enter adds a new line (and Enter while composing, e.g. IME input, doesn't send).
  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault()
      sendMessage(draft)
    }
  }

  const tooLong = draft.length > CHAT_MESSAGE_MAX_LENGTH
  const canSend = draft.trim() !== '' && !tooLong && !send.isPending

  return (
    <div className={panelClassName}>
      <header className="flex items-center gap-3 border-b px-4 py-3">
        <div className="flex size-10 items-center justify-center rounded-full bg-amber-500/15 text-amber-600 dark:text-amber-400">
          <FlaskConical className="size-5" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold">Chatting with {businessName}</p>
          <p className="text-muted-foreground truncate text-xs">
            You're the customer <span className="font-medium">{SANDBOX_DISPLAY_NAME}</span> ({SANDBOX_PHONE_NUMBER})
          </p>
        </div>
        <Badge variant="outline" className="hidden sm:inline-flex">
          Sandbox
        </Badge>
        <Button
          variant="ghost"
          size="icon"
          aria-label="Reload conversation"
          title="Reload conversation"
          disabled={session.isFetching || send.isPending}
          onClick={() => session.refetch()}
        >
          <RefreshCw className={session.isFetching ? 'animate-spin' : undefined} />
        </Button>
      </header>

      <div className="bg-muted/20 flex-1 overflow-y-auto px-4 py-4">
        {messages.length === 0 && !send.isPending ? (
          <div className="flex h-full flex-col items-center justify-center gap-3 text-center">
            <MessageSquareDashed className="text-muted-foreground size-10" />
            <p className="font-medium">Start the conversation</p>
            <p className="text-muted-foreground max-w-sm text-sm">
              Send a message as if you were a customer, and see how your assistant replies.
            </p>
            <div className="flex flex-wrap justify-center gap-2">
              {SUGGESTIONS.map((suggestion) => (
                <Button key={suggestion} variant="outline" size="sm" onClick={() => sendMessage(suggestion)}>
                  {suggestion}
                </Button>
              ))}
            </div>
          </div>
        ) : (
          <ul className="flex flex-col gap-3" aria-live="polite">
            {messages.map((message, index) => (
              <ChatMessageBubble key={`${index}-${message.message_time}`} message={message} />
            ))}
            {send.isPending && <TypingBubble />}
          </ul>
        )}
        <div ref={endRef} />
      </div>

      {send.error && <SendError error={send.error} />}

      <form onSubmit={onSubmit} className="flex items-end gap-2 border-t p-3">
        <div className="grid flex-1 gap-1">
          <Textarea
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Type a message as the customer…"
            aria-label="Message"
            aria-invalid={tooLong || undefined}
            rows={1}
            className="max-h-40 min-h-10 resize-none"
          />
          {draft.length > CHAT_MESSAGE_MAX_LENGTH - 500 && (
            <p className={`text-right text-xs ${tooLong ? 'text-destructive' : 'text-muted-foreground'}`}>
              {draft.length} / {CHAT_MESSAGE_MAX_LENGTH}
            </p>
          )}
        </div>
        <Button type="submit" size="icon" className="size-10" disabled={!canSend} aria-label="Send message">
          <SendHorizontal />
        </Button>
      </form>
    </div>
  )
}

function SendError({ error }: { error: ApiError }) {
  const { fields, form } = getFormErrors(error)
  const detail = Object.values(fields).join(' ') || form || error.message
  // 5xx: the LLM failed, but the backend already saved the customer's message.
  const isLlmError = error.status !== undefined && error.status >= 500
  return (
    <p role="alert" className="text-destructive flex items-start gap-2 border-t px-4 py-2 text-sm">
      <CircleAlert className="mt-0.5 size-4 shrink-0" />
      <span>
        {isLlmError ? "The assistant couldn't reply: " : "Couldn't send your message: "}
        {detail}
        {isLlmError && ' Your message was still saved.'}
      </span>
    </p>
  )
}

function ErrorPanel({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className={`${panelClassName} items-center justify-center gap-3 p-6 text-center`}>
      <CircleAlert className="text-destructive size-8" />
      <p className="text-destructive max-w-md text-sm">{message}</p>
      {onRetry && (
        <Button variant="outline" size="sm" onClick={() => onRetry()}>
          Try again
        </Button>
      )}
    </div>
  )
}
