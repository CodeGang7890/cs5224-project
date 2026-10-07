import type { ReactNode } from 'react'
import { useSearchParams } from 'react-router'

import { APP_NAME } from '@/config/app'
import { ChatSessionBrowser } from '@/features/chat-sessions'
import { OpenQuestionsAlert, QuestionsBrowser, useOpenQuestionCount } from '@/features/questions'
import { cn } from '@/lib/utils'

type ChatsTab = 'conversations' | 'questions'

export function ChatsPage() {
  // The sub-tab is in the URL (`?tab=questions`), like the rest of the page's state.
  const [searchParams, setSearchParams] = useSearchParams()
  const tab: ChatsTab = searchParams.get('tab') === 'questions' ? 'questions' : 'conversations'
  const { data: openCount = 0 } = useOpenQuestionCount()
  // Each sub-tab has its own filters, so switching starts from a clean URL.
  const showTab = (next: ChatsTab) => setSearchParams(next === 'questions' ? { tab: 'questions' } : {})

  return (
    <section className="flex flex-col gap-6">
      <title>{`Chats | ${APP_NAME}`}</title>
      <div className="grid gap-1">
        <h1 className="text-2xl font-bold tracking-tight">Chats</h1>
        <p className="text-muted-foreground text-sm">
          Browse your business's conversations with customers, and answer the questions the assistant couldn't.
        </p>
      </div>

      <div role="tablist" aria-label="Chats" className="flex gap-1 border-b">
        <TabButton active={tab === 'conversations'} onClick={() => showTab('conversations')}>
          Conversations
        </TabButton>
        <TabButton active={tab === 'questions'} onClick={() => showTab('questions')}>
          Unanswered questions
          {openCount > 0 && (
            <span
              className="bg-destructive ml-2 inline-flex min-w-5 items-center justify-center rounded-full px-1.5 text-xs font-semibold text-white tabular-nums"
              aria-label={`${openCount} need an answer`}
            >
              {openCount}
            </span>
          )}
        </TabButton>
      </div>

      {tab === 'conversations' ? (
        <>
          <OpenQuestionsAlert onView={() => showTab('questions')} />
          <ChatSessionBrowser />
        </>
      ) : (
        <QuestionsBrowser />
      )}
    </section>
  )
}

function TabButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={onClick}
      className={cn(
        '-mb-px inline-flex items-center border-b-2 px-3 py-2 text-sm font-medium transition-colors',
        active ? 'border-primary text-foreground' : 'text-muted-foreground hover:text-foreground border-transparent',
      )}
    >
      {children}
    </button>
  )
}
