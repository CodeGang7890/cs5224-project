import { APP_NAME } from '@/config/app'
import { ChatSandbox } from '@/features/chat-sessions'

export function ChatSandboxPage() {
  return (
    <section className="flex flex-col gap-6">
      <title>{`Chat Sandbox | ${APP_NAME}`}</title>
      <div className="grid gap-1">
        <h1 className="text-2xl font-bold tracking-tight">Chat Sandbox</h1>
        <p className="text-muted-foreground text-sm">
          Try out your chat assistant by pretending to be a customer. Start as many test chats as you like: each
          one is a separate conversation, kept apart from your real customer chats.
        </p>
      </div>
      <ChatSandbox />
    </section>
  )
}
