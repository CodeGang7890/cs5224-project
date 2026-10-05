import { APP_NAME } from '@/config/app'
import { ChatSessionBrowser } from '@/features/chat-sessions'

export function ChatsPage() {
  return (
    <section className="flex flex-col gap-6">
      <title>{`Chats | ${APP_NAME}`}</title>
      <div className="grid gap-1">
        <h1 className="text-2xl font-bold tracking-tight">Chats</h1>
        <p className="text-muted-foreground text-sm">
          Browse your business's conversations with customers. This page is read only.
        </p>
      </div>
      <ChatSessionBrowser />
    </section>
  )
}
