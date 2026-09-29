import { useCallback, useEffect, useMemo, useRef, useState, type DragEvent } from 'react'
import {
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  ReactFlow,
  useEdgesState,
  useNodesState,
  useReactFlow,
  type Connection,
  type Edge,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { CircleAlert, CircleCheck, Info, Save, Undo2 } from 'lucide-react'
import { useBlocker } from 'react-router'

import { ConfirmDialog } from '@/components/common/confirm-dialog'
import { Button } from '@/components/ui/button'
import { getFormErrors } from '@/lib/form-errors'
import { useThemeStore } from '@/stores/theme-store'
import type { ApiError } from '@/types/api'

import { BLOCK_HEIGHT, BLOCK_WIDTH } from '../blocks'
import {
  configToFlow,
  countUnreachableBlocks,
  createBlockNode,
  createEdge,
  DEFAULT_CONFIG,
  flowToConfig,
  type BlockNode,
} from '../flow'
import { useSaveChatConfiguration } from '../hooks/use-chat-configuration'
import { ADDABLE_BLOCK_TYPES, type BlockType, type ChatBlock, type ChatConfiguration } from '../types'
import { BLOCK_DRAG_TYPE, BlockPalette } from './block-palette'
import { BlockNodeView } from './block-node'
import { DeletableEdge } from './deletable-edge'

// Defined outside the component so React Flow doesn't see new types on every render.
const nodeTypes = { block: BlockNodeView }
const edgeTypes = { deletable: DeletableEdge }

interface WorkflowEditorProps {
  /** Last saved configuration (from the GET query); `null` if the business hasn't saved one yet. */
  configuration: ChatConfiguration | null
  /** Re-fetches the configuration from the API; used by Discard. */
  refetch: () => Promise<{ data?: ChatConfiguration | null; error: ApiError | null }>
}

/** Canvas + palette + save/discard. Must be rendered inside a `ReactFlowProvider`. */
export function WorkflowEditor({ configuration, refetch }: WorkflowEditorProps) {
  const theme = useThemeStore((state) => state.theme)
  const { screenToFlowPosition } = useReactFlow()
  const canvasRef = useRef<HTMLDivElement>(null)

  const savedConfig = configuration?.config_json ?? DEFAULT_CONFIG
  const initialFlow = useMemo(() => configToFlow(savedConfig), [savedConfig])
  const [nodes, setNodes, onNodesChange] = useNodesState<BlockNode>(initialFlow.nodes)
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>(initialFlow.edges)

  const currentConfig = useMemo(() => flowToConfig(nodes, edges), [nodes, edges])
  const savedJson = useMemo(
    () => JSON.stringify(flowToConfig(initialFlow.nodes, initialFlow.edges)),
    [initialFlow],
  )
  const isDirty = JSON.stringify(currentConfig) !== savedJson
  const unreachableCount = countUnreachableBlocks(currentConfig)

  const resetTo = useCallback(
    (config: ChatBlock[]) => {
      const flow = configToFlow(config)
      setNodes(flow.nodes)
      setEdges(flow.edges)
    },
    [setNodes, setEdges],
  )

  // --- Editing --------------------------------------------------------------------------

  const addBlock = useCallback(
    (blockType: BlockType, position: { x: number; y: number }) => {
      setNodes((current) => [...current, createBlockNode(crypto.randomUUID(), blockType, position)])
    },
    [setNodes],
  )

  // Clicking + in the palette: drop the block in the middle of the visible canvas, nudged so
  // repeated clicks don't stack blocks exactly on top of each other.
  const addBlockAtCentre = (blockType: BlockType) => {
    const rect = canvasRef.current?.getBoundingClientRect()
    if (!rect) return
    const centre = screenToFlowPosition({ x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 })
    const nudge = (nodes.length % 5) * 24
    addBlock(blockType, { x: centre.x - BLOCK_WIDTH / 2 + nudge, y: centre.y - BLOCK_HEIGHT / 2 + nudge })
  }

  const onDragOver = (event: DragEvent) => {
    if (!event.dataTransfer.types.includes(BLOCK_DRAG_TYPE)) return
    event.preventDefault()
    event.dataTransfer.dropEffect = 'move'
  }

  const onDrop = (event: DragEvent) => {
    const blockType = event.dataTransfer.getData(BLOCK_DRAG_TYPE) as BlockType
    if (!(ADDABLE_BLOCK_TYPES as readonly string[]).includes(blockType)) return
    event.preventDefault()
    const position = screenToFlowPosition({ x: event.clientX, y: event.clientY })
    addBlock(blockType, { x: position.x - BLOCK_WIDTH / 2, y: position.y - BLOCK_HEIGHT / 2 })
  }

  // Each block has one next block, so a new arrow replaces the source's existing one.
  const onConnect = useCallback(
    ({ source, target }: Connection) => {
      setEdges((current) => [...current.filter((edge) => edge.source !== source), createEdge(source, target)])
    },
    [setEdges],
  )

  // --- Save / discard -------------------------------------------------------------------

  const save = useSaveChatConfiguration()
  const [saveOpen, setSaveOpen] = useState(false)
  const [discardOpen, setDiscardOpen] = useState(false)
  const [isDiscarding, setIsDiscarding] = useState(false)
  const [discardError, setDiscardError] = useState<string | null>(null)
  const saveErrors = save.error ? getFormErrors(save.error) : null
  const saveErrorMessage = saveErrors && (saveErrors.fields.config_json ?? saveErrors.form ?? save.error?.message)

  const onConfirmSave = () => {
    save.mutate(
      { config_json: currentConfig },
      {
        onSuccess: (saved) => {
          resetTo(saved.config_json)
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
    if (result.error) {
      setDiscardError(`Couldn't load the saved workflow: ${result.error.message}`)
      return
    }
    resetTo(result.data?.config_json ?? DEFAULT_CONFIG)
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

  const blockCount = currentConfig.length

  return (
    <div className="flex flex-col gap-3">
      <div className="flex min-h-9 flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
          {isDirty ? (
            <span className="flex items-center gap-1.5 font-medium text-amber-600 dark:text-amber-400">
              <span className="size-2 rounded-full bg-current" /> Unsaved changes
            </span>
          ) : configuration ? (
            <span className="text-muted-foreground flex items-center gap-1.5">
              <CircleCheck className="size-4 text-emerald-600 dark:text-emerald-400" />
              Saved {new Date(configuration.last_updated).toLocaleString()}
            </span>
          ) : (
            <span className="text-muted-foreground flex items-center gap-1.5">
              <Info className="size-4" /> No workflow saved yet. Add some blocks and save to create one.
            </span>
          )}
          {unreachableCount > 0 && (
            <span className="text-muted-foreground flex items-center gap-1.5">
              <CircleAlert className="size-4 text-amber-500" />
              {unreachableCount} block{unreachableCount === 1 ? " isn't" : "s aren't"} connected to Start
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

      <div className="bg-card flex h-[calc(100svh-16rem)] min-h-[520px] overflow-hidden rounded-xl border">
        <BlockPalette onAdd={addBlockAtCentre} />
        <div ref={canvasRef} className="relative flex-1" onDragOver={onDragOver} onDrop={onDrop}>
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            isValidConnection={(connection) => connection.source !== connection.target}
            nodeTypes={nodeTypes}
            edgeTypes={edgeTypes}
            deleteKeyCode={['Backspace', 'Delete']}
            colorMode={theme}
            fitView
            fitViewOptions={{ padding: 0.3, maxZoom: 1 }}
          >
            <Background variant={BackgroundVariant.Dots} gap={18} size={1.5} />
            <Controls showInteractive={false} />
            <MiniMap pannable zoomable className="hidden! md:block!" />
          </ReactFlow>
        </div>
      </div>

      <ConfirmDialog
        open={saveOpen}
        onOpenChange={setSaveOpen}
        title="Save workflow?"
        description={
          <span className="grid gap-2">
            <span>
              This replaces your saved chat workflow with the current {blockCount} block{blockCount === 1 ? '' : 's'}.
            </span>
            {unreachableCount > 0 && (
              <span>
                {unreachableCount} block{unreachableCount === 1 ? " isn't" : "s aren't"} connected to Start, so the
                chat won't reach {unreachableCount === 1 ? 'it' : 'them'}.
              </span>
            )}
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
