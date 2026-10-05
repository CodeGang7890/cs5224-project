import { useState } from 'react'
import { CircleAlert, FlaskConical, Plus, Workflow } from 'lucide-react'
import { Link, useSearchParams } from 'react-router'

import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { paths } from '@/config/navigation'
import { useCurrentUser } from '@/features/auth'

import { useCreateSandboxSession, useSandboxSessions } from '../hooks/use-chat-sessions'
import { isMissingChatConfiguration, nextSandboxChatName } from '../sandbox'
import { SandboxChatWindow } from './sandbox-chat-window'
import { SandboxDebugPanel } from './sandbox-debug-panel'
import { SandboxSessionList } from './sandbox-session-list'

const SESSION_PARAM = 'session'
/** Present (`?debug`) while the debug panel is open. */
const DEBUG_PARAM = 'debug'

const panelClassName = 'flex h-[calc(100svh-16rem)] min-h-[520px] overflow-hidden rounded-xl border'

/**
 * Sandbox chats: test your assistant as a pretend customer, in as many separate chats as you
 * like. The selected chat is kept in the URL (`?session=<id>`). Needs a logged-in business user.
 */
export function ChatSandbox() {
  const { data: user, isPending, error, refetch } = useCurrentUser()

  if (isPending) return <Skeleton className={panelClassName} />
  if (error) return <ErrorMessage text={`Couldn't load your account: ${error.message}`} onRetry={refetch} />
  if (user.business === null) {
    return <ErrorMessage text="Your account isn't linked to a business, so there's no assistant to chat with." />
  }
  return <SandboxChats businessName={user.business_name ?? 'your business'} />
}

function SandboxChats({ businessName }: { businessName: string }) {
  const sessionsQuery = useSandboxSessions()
  const create = useCreateSandboxSession()
  const [searchParams, setSearchParams] = useSearchParams()
  // Unsent text per chat, so switching chats doesn't lose what you were typing.
  const [drafts, setDrafts] = useState<Record<number, string>>({})

  const sessions = sessionsQuery.data?.pages.flatMap((page) => page.results) ?? []
  const requestedId = Number(searchParams.get(SESSION_PARAM))
  const debugOpen = searchParams.has(DEBUG_PARAM)
  // Unknown or deleted ID (or none): fall back to the most recent chat.
  const selected = sessions.find((s) => s.id === requestedId) ?? sessions[0]

  const select = (id: number | null) =>
    setSearchParams(
      (params) => {
        if (id === null) params.delete(SESSION_PARAM)
        else params.set(SESSION_PARAM, String(id))
        return params
      },
      { replace: true },
    )

  const setDebugOpen = (open: boolean) =>
    setSearchParams(
      (params) => {
        if (open) params.set(DEBUG_PARAM, '')
        else params.delete(DEBUG_PARAM)
        return params
      },
      { replace: true },
    )

  const createChat = () =>
    create.mutate({ display_name: nextSandboxChatName(sessions) }, { onSuccess: (session) => select(session.id) })

  if (sessionsQuery.isPending) {
    return (
      <div className={panelClassName} aria-busy="true" aria-label="Loading sandbox chats">
        <div className="grid w-72 content-start gap-2 border-r p-3">
          <Skeleton className="h-9 w-full" />
          {Array.from({ length: 4 }, (_, i) => (
            <Skeleton key={i} className="h-14 w-full" />
          ))}
        </div>
        <div className="flex flex-1 flex-col gap-3 p-4">
          <Skeleton className="h-10 w-56" />
          <Skeleton className="ml-auto h-12 w-2/5" />
          <Skeleton className="h-16 w-1/2" />
        </div>
      </div>
    )
  }

  if (sessionsQuery.isError && !sessionsQuery.data) {
    return (
      <ErrorMessage
        text={`Couldn't load your sandbox chats: ${sessionsQuery.error.message}`}
        onRetry={sessionsQuery.refetch}
      />
    )
  }

  const createError = create.error && (
    <div role="alert" className="text-destructive border-b px-3 py-2 text-xs">
      {isMissingChatConfiguration(create.error) ? (
        <span>
          Set up your workflow first: chats start at its Start block.{' '}
          <Link to={paths.workflow} className="font-medium underline underline-offset-2">
            Go to Workflow
          </Link>
        </span>
      ) : (
        <span>Couldn't create a chat: {create.error.message}</span>
      )}
    </div>
  )

  return (
    <div className={`${panelClassName} flex-col md:flex-row`}>
      <aside className="bg-muted/30 flex max-h-56 w-full shrink-0 flex-col border-b md:max-h-none md:w-72 md:border-r md:border-b-0">
        <div className="flex items-center justify-between gap-2 border-b px-3 py-2.5">
          <div>
            <h2 className="text-sm font-semibold">Sandbox chats</h2>
            <p className="text-muted-foreground text-xs">
              {sessions.length} chat{sessions.length === 1 ? '' : 's'}
            </p>
          </div>
          <Button size="sm" onClick={createChat} disabled={create.isPending}>
            <Plus /> {create.isPending ? 'Creating…' : 'New chat'}
          </Button>
        </div>
        {createError}
        <SandboxSessionList
          sessions={sessions}
          selectedId={selected?.id}
          onSelect={select}
          hasMore={sessionsQuery.hasNextPage}
          isLoadingMore={sessionsQuery.isFetchingNextPage}
          onLoadMore={() => sessionsQuery.fetchNextPage()}
        />
      </aside>

      {selected ? (
        <>
          <SandboxChatWindow
            key={selected.id}
            session={selected}
            businessName={businessName}
            draft={drafts[selected.id] ?? ''}
            onDraftChange={(draft) => setDrafts((current) => ({ ...current, [selected.id]: draft }))}
            onDeleted={() => select(null)}
            debugOpen={debugOpen}
            onDebugOpenChange={setDebugOpen}
          />
          {debugOpen && <SandboxDebugPanel session={selected} onClose={() => setDebugOpen(false)} />}
        </>
      ) : (
        <div className="flex flex-1 flex-col items-center justify-center gap-3 p-6 text-center">
          <FlaskConical className="text-muted-foreground size-10" />
          <p className="font-medium">No sandbox chats yet</p>
          <p className="text-muted-foreground max-w-sm text-sm">
            Start a test chat to see how your assistant replies to customers. You can have as many as you like.
          </p>
          <Button onClick={createChat} disabled={create.isPending}>
            <Plus /> {create.isPending ? 'Creating…' : 'New chat'}
          </Button>
          {create.error && isMissingChatConfiguration(create.error) && (
            <Button variant="outline" asChild>
              <Link to={paths.workflow}>
                <Workflow /> Set up your workflow
              </Link>
            </Button>
          )}
        </div>
      )}
    </div>
  )
}

function ErrorMessage({ text, onRetry }: { text: string; onRetry?: () => void }) {
  return (
    <div className={`${panelClassName} flex-col items-center justify-center gap-3 p-6 text-center`}>
      <CircleAlert className="text-destructive size-8" />
      <p className="text-destructive max-w-md text-sm">{text}</p>
      {onRetry && (
        <Button variant="outline" size="sm" onClick={() => onRetry()}>
          Try again
        </Button>
      )}
    </div>
  )
}
