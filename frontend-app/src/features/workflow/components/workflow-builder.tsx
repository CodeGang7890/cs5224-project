import { ReactFlowProvider } from '@xyflow/react'
import { CircleAlert } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'

import { useChatConfiguration } from '../hooks/use-chat-configuration'
import { WorkflowEditor } from './workflow-editor'

/** Loads the business's chat configuration, then shows the editor (or a loading / error state). */
export function WorkflowBuilder() {
  const { data, isPending, error, refetch, isFetching } = useChatConfiguration()

  if (isPending) {
    return (
      <div className="flex flex-col gap-3" aria-busy="true" aria-label="Loading workflow">
        <Skeleton className="h-9 w-64" />
        <div className="flex h-[calc(100svh-16rem)] min-h-[520px] gap-3 rounded-xl border p-3">
          <div className="grid w-60 content-start gap-2">
            {Array.from({ length: 3 }, (_, i) => (
              <Skeleton key={i} className="h-20 w-full" />
            ))}
          </div>
          <Skeleton className="flex-1" />
        </div>
      </div>
    )
  }

  // `data` is null (not undefined) when there's simply no configuration yet. If a later
  // re-fetch fails, keep showing the editor so unsaved edits aren't lost.
  if (data === undefined) {
    const message =
      error?.status === 403
        ? "Your account isn't linked to a business, so there's no workflow to edit."
        : `Couldn't load your workflow: ${error?.message ?? 'Unknown error'}`
    return (
      <div className="border-destructive/50 flex flex-col items-start gap-3 rounded-lg border p-4">
        <p className="text-destructive flex items-center gap-2 text-sm">
          <CircleAlert className="size-4" /> {message}
        </p>
        {error?.status !== 403 && (
          <Button variant="outline" size="sm" disabled={isFetching} onClick={() => refetch()}>
            {isFetching ? 'Retrying…' : 'Try again'}
          </Button>
        )}
      </div>
    )
  }

  return (
    <ReactFlowProvider>
      <WorkflowEditor configuration={data} refetch={refetch} />
    </ReactFlowProvider>
  )
}
