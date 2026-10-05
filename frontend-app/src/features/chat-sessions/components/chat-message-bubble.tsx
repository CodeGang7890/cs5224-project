import { Bot, Store, UserRound } from 'lucide-react'

import { cn } from '@/lib/utils'

import type { ChatMessage, SentBy } from '../types'

const SENDER: Record<SentBy, { label: string; icon: typeof Bot }> = {
  customer: { label: 'Customer', icon: UserRound },
  'business-automated': { label: 'Assistant', icon: Bot },
  'business-manual': { label: 'Business', icon: Store },
}

function formatTime(iso: string) {
  return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

interface ChatMessageBubbleProps {
  message: ChatMessage
  /**
   * Whose side "you" are on. `customer` (Chat Sandbox): your customer messages on the right.
   * `business` (Chats tab): the business's messages on the right, each labelled Assistant or Business.
   */
  perspective?: 'customer' | 'business'
}

/** One chat message bubble. */
export function ChatMessageBubble({ message, perspective = 'customer' }: ChatMessageBubbleProps) {
  const fromCustomer = message.sent_by === 'customer'
  const onRight = perspective === 'customer' ? fromCustomer : !fromCustomer
  const sender = SENDER[message.sent_by]
  const showSender = !onRight || perspective === 'business'

  return (
    <li className={cn('flex gap-2', onRight ? 'flex-row-reverse' : 'flex-row')}>
      {showSender && (
        <div className="bg-muted text-muted-foreground mt-auto flex size-7 shrink-0 items-center justify-center rounded-full">
          <sender.icon className="size-4" />
        </div>
      )}
      <div
        className={cn(
          'max-w-[75%] rounded-2xl px-3.5 py-2 text-sm shadow-xs',
          onRight ? 'bg-primary text-primary-foreground rounded-br-sm' : 'bg-muted rounded-bl-sm',
        )}
      >
        {showSender && (
          <p className={cn('mb-0.5 text-xs font-medium', onRight ? 'text-primary-foreground/70' : 'text-muted-foreground')}>
            {sender.label}
          </p>
        )}
        <p className="break-words whitespace-pre-wrap">{message.message}</p>
        <p
          className={cn('mt-1 text-right text-[11px]', onRight ? 'text-primary-foreground/70' : 'text-muted-foreground')}
          title={new Date(message.message_time).toLocaleString()}
        >
          {formatTime(message.message_time)}
        </p>
      </div>
    </li>
  )
}

/** "The assistant is typing" bubble, shown while waiting for the reply. */
export function TypingBubble() {
  return (
    <li className="flex justify-start gap-2" aria-label="Waiting for the assistant's reply">
      <div className="bg-muted text-muted-foreground mt-auto flex size-7 shrink-0 items-center justify-center rounded-full">
        <Bot className="size-4" />
      </div>
      <div className="bg-muted flex items-center gap-1 rounded-2xl rounded-bl-sm px-4 py-3">
        {[0, 150, 300].map((delay) => (
          <span
            key={delay}
            className="bg-muted-foreground/60 size-1.5 animate-bounce rounded-full"
            style={{ animationDelay: `${delay}ms` }}
          />
        ))}
      </div>
    </li>
  )
}
