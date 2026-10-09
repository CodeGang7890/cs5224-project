import { TabPage } from '@/components/common/tab-page'
import { ChatSandbox } from '@/features/chat-sessions'

export function ChatSandboxPage() {
  return (
    <TabPage
      title="Chat Sandbox"
      section="Chats"
      description="Try out your chat assistant by pretending to be a customer. Start as many test chats as you like: each one is a separate conversation, kept apart from your real customer chats."
    >
      <ChatSandbox />
    </TabPage>
  )
}
