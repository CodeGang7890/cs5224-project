import { Bot, UserRound } from 'lucide-react'

import { cn } from '@/lib/utils'

import type { ChatMessage } from '../types'

const BUSINESS_SENDER = {
  'business-automated': { label: 'Assistant', icon: Bot },
  'business-manual': { label: 'Business', icon: UserRound },
} as const

function formatTime(iso: string) {
  return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

/** One message. The customer (you, in the sandbox) is on the right; the business on the left. */
export function ChatMessageBubble({ message }: { message: ChatMessage }) {
  const fromCustomer = message.sent_by === 'customer'
  const sender = message.sent_by === 'customer' ? null : BUSINESS_SENDER[message.sent_by]

  return (
    <li className={cn('flex gap-2', fromCustomer ? 'justify-end' : 'justify-start')}>
      {sender && (
        <div className="bg-muted text-muted-foreground mt-auto flex size-7 shrink-0 items-center justify-center rounded-full">
          <sender.icon className="size-4" />
        </div>
      )}
      <div
        className={cn(
          'max-w-[75%] rounded-2xl px-3.5 py-2 text-sm shadow-xs',
          fromCustomer ? 'bg-primary text-primary-foreground rounded-br-sm' : 'bg-muted rounded-bl-sm',
        )}
      >
        {sender && <p className="text-muted-foreground mb-0.5 text-xs font-medium">{sender.label}</p>}
        <p className="break-words whitespace-pre-wrap">{message.message}</p>
        <p
          className={cn(
            'mt-1 text-right text-[11px]',
            fromCustomer ? 'text-primary-foreground/70' : 'text-muted-foreground',
          )}
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
