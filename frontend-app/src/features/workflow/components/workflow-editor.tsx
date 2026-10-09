import { useEffect, useState } from 'react'
import { Background, BackgroundVariant, Controls, ReactFlow, useNodesState } from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { CircleCheck, Info, Save, Undo2 } from 'lucide-react'
import { useBlocker } from 'react-router'

import { ConfirmDialog } from '@/components/common/confirm-dialog'
import { Button } from '@/components/ui/button'
import { getFormErrors } from '@/lib/form-errors'
import { useThemeStore } from '@/stores/theme-store'
import type { ApiError } from '@/types/api'

import { normalizeDetailField } from '../details'
import { FLOW_EDGES, flowNodes, type StepNode } from '../diagram'
import { useSaveChatConfiguration } from '../hooks/use-chat-configuration'
import { DETAILS_NODES, type FlowNodeId } from '../steps'
import type { ChatConfiguration, DetailField } from '../types'
import { DetailFieldsDialog } from './detail-fields-dialog'
import { StepInfoDialog } from './step-info-dialog'
import { StepNodeView } from './step-node'

// Defined outside the component so React Flow doesn't see new types on every render.
const nodeTypes = { step: StepNodeView }

/** Fixed key order, so comparing JSON tells whether anything changed. */
function normalized(fields: DetailField[]): DetailField[] {
  return fields.map(normalizeDetailField)
}

interface WorkflowEditorProps {
  /** Last saved configuration (from the GET query); the defaults if the business never saved one. */
  configuration: ChatConfiguration
  /** Re-fetches the configuration from the API; used by Discard. */
  refetch: () => Promise<{ data?: ChatConfiguration; error: ApiError | null }>
}

/**
 * The chat flow, as a fixed diagram: the router and its branches. The flow can't change, but
 * clicking a block shows what it does, and the Details collection block's details can be edited
 * (then saved). Must be rendered inside a `ReactFlowProvider`.
 */
export function WorkflowEditor({ configuration, refetch }: WorkflowEditorProps) {
  const theme = useThemeStore((state) => state.theme)

  const savedFields = configuration.detail_fields
  const [fields, setFields] = useState<DetailField[]>(savedFields)
  const isDirty = JSON.stringify(normalized(fields)) !== JSON.stringify(normalized(savedFields))

  const [nodes, setNodes, onNodesChange] = useNodesState<StepNode>(flowNodes(savedFields))
  // The details blocks list the (maybe unsaved) details.
  useEffect(() => {
    setNodes((current) =>
      current.map((node) => (DETAILS_NODES.includes(node.data.nodeId) ? { ...node, data: { ...node.data, fields } } : node)),
    )
  }, [fields, setNodes])

  const [openNode, setOpenNode] = useState<FlowNodeId | null>(null)
  const detailsOpen = openNode !== null && DETAILS_NODES.includes(openNode)

  // --- Save / discard -------------------------------------------------------------------

  const save = useSaveChatConfiguration()
  const [saveOpen, setSaveOpen] = useState(false)
  const [discardOpen, setDiscardOpen] = useState(false)
  const [isDiscarding, setIsDiscarding] = useState(false)
  const [discardError, setDiscardError] = useState<string | null>(null)
  const saveErrors = save.error ? getFormErrors(save.error) : null
  const saveErrorMessage = saveErrors && (saveErrors.fields.detail_fields ?? saveErrors.form ?? save.error?.message)

  const onConfirmSave = () => {
    save.mutate(
      { detail_fields: normalized(fields) },
      {
        onSuccess: (saved) => {
          setFields(saved.detail_fields)
          setSaveOpen(false)
        },
      },
    )
  }

  // Discard goes back to what's saved on the server: re-fetch it rather than keeping a local copy.
  const onConfirmDiscard = async () => {
    setIsDiscarding(true)
    setDiscardError(null)
    const result = await refetch()
    setIsDiscarding(false)
    if (result.error || !result.data) {
      setDiscardError(`Couldn't load the saved workflow: ${result.error?.message ?? 'Unknown error'}`)
      return
    }
    setFields(result.data.detail_fields)
    setDiscardOpen(false)
  }

  // --- Unsaved changes guard ------------------------------------------------------------

  const blocker = useBlocker(
    ({ currentLocation, nextLocation }) => isDirty && currentLocation.pathname !== nextLocation.pathname,
  )

  useEffect(() => {
    if (!isDirty) return
    const onBeforeUnload = (event: BeforeUnloadEvent) => event.preventDefault()
    window.addEventListener('beforeunload', onBeforeUnload)
    return () => window.removeEventListener('beforeunload', onBeforeUnload)
  }, [isDirty])

  return (
    <div className="flex flex-col gap-3">
      <div className="flex min-h-9 flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
          {isDirty ? (
            <span className="flex items-center gap-1.5 font-medium text-amber-600 dark:text-amber-400">
              <span className="size-2 rounded-full bg-current" /> Unsaved changes
            </span>
          ) : configuration.last_updated ? (
            <span className="text-muted-foreground flex items-center gap-1.5">
              <CircleCheck className="size-4 text-emerald-600 dark:text-emerald-400" />
              Saved {new Date(configuration.last_updated).toLocaleString()}
            </span>
          ) : (
            <span className="text-muted-foreground flex items-center gap-1.5">
              <Info className="size-4" /> Using the default settings. Click Details collection to change them.
            </span>
          )}
        </div>
        {isDirty && (
          <div className="flex gap-2">
            <Button
              variant="outline"
              onClick={() => {
                setDiscardError(null)
                setDiscardOpen(true)
              }}
            >
              <Undo2 /> Discard changes
            </Button>
            <Button
              onClick={() => {
                save.reset()
                setSaveOpen(true)
              }}
            >
              <Save /> Save changes
            </Button>
          </div>
        )}
      </div>

      <div className="bg-card h-[calc(100svh-16rem)] min-h-[520px] overflow-hidden rounded-xl border">
        <ReactFlow
          nodes={nodes}
          edges={FLOW_EDGES}
          onNodesChange={onNodesChange}
          onNodeClick={(_event, node) => setOpenNode(node.data.nodeId)}
          nodeTypes={nodeTypes}
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable={false}
          deleteKeyCode={null}
          colorMode={theme}
          fitView
          fitViewOptions={{ padding: 0.15, maxZoom: 1 }}
        >
          <Background variant={BackgroundVariant.Dots} gap={18} size={1.5} />
          <Controls showInteractive={false} />
        </ReactFlow>
      </div>

      <DetailFieldsDialog
        open={detailsOpen}
        onOpenChange={(open) => !open && setOpenNode(null)}
        fields={fields}
        onApply={setFields}
      />

      <StepInfoDialog nodeId={detailsOpen ? null : openNode} onClose={() => setOpenNode(null)} />

      <ConfirmDialog
        open={saveOpen}
        onOpenChange={setSaveOpen}
        title="Save workflow?"
        description={
          <span className="grid gap-2">
            <span>
              The assistant will ask new customers for these {fields.length} detail{fields.length === 1 ? '' : 's'}{' '}
              at the Details collection and Booking details steps.
            </span>
            {saveErrorMessage && (
              <span role="alert" className="text-destructive">
                Couldn't save: {saveErrorMessage}
              </span>
            )}
          </span>
        }
        confirmLabel="Save"
        pendingLabel="Saving…"
        isPending={save.isPending}
        onConfirm={onConfirmSave}
      />

      <ConfirmDialog
        open={discardOpen}
        onOpenChange={setDiscardOpen}
        title="Discard changes?"
        description={
          <span className="grid gap-2">
            <span>Your unsaved changes will be lost, and the workflow goes back to the last saved version.</span>
            {discardError && (
              <span role="alert" className="text-destructive">
                {discardError}
              </span>
            )}
          </span>
        }
        confirmLabel="Discard"
        pendingLabel="Loading saved workflow…"
        destructive
        isPending={isDiscarding}
        onConfirm={onConfirmDiscard}
      />

      <ConfirmDialog
        open={blocker.state === 'blocked'}
        onOpenChange={(open) => !open && blocker.reset?.()}
        title="Leave without saving?"
        description="You have unsaved changes to your workflow. They'll be lost if you leave this page."
        confirmLabel="Leave page"
        destructive
        onConfirm={() => blocker.proceed?.()}
      />
    </div>
  )
}
