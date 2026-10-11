import { ReactFlowProvider } from '@xyflow/react'
import { CircleAlert } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'

import type { FlowRoute } from '../diagram'
import { useChatConfiguration } from '../hooks/use-chat-configuration'
import { WorkflowEditor } from './workflow-editor'

interface WorkflowBuilderProps {
  /** Routes customers can't take right now (e.g. no products), greyed out in the diagram. */
  unavailableRoutes?: FlowRoute[]
}

/** Loads the business's chat configuration, then shows the editor (or a loading / error state). */
export function WorkflowBuilder({ unavailableRoutes = [] }: WorkflowBuilderProps) {
  const { data, isPending, error, refetch, isFetching } = useChatConfiguration()

  if (isPending) {
    return (
      <div className="flex flex-col gap-3" aria-busy="true" aria-label="Loading workflow">
        <Skeleton className="h-9 w-64" />
        <Skeleton className="h-[calc(100svh-16rem)] min-h-[520px] rounded-xl" />
      </div>
    )
  }

  // If a later re-fetch fails, keep showing the editor so unsaved edits aren't lost.
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
      <WorkflowEditor configuration={data} refetch={refetch} unavailableRoutes={unavailableRoutes} />
    </ReactFlowProvider>
  )
}
