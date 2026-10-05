import type { ReactNode } from 'react'
import { Bug, CircleCheck, CircleDashed, Undo2, X } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { BLOCK_META, useChatConfiguration, type BlockType } from '@/features/workflow'

import { useSandboxTurnDebug } from '../hooks/use-chat-sessions'
import type { ChatSession, FlowStepDebug } from '../types'

function blockLabel(blockType: string | undefined): string {
  if (!blockType) return 'Unknown block'
  return BLOCK_META[blockType as BlockType]?.label ?? blockType
}

interface SandboxDebugPanelProps {
  session: ChatSession
  onClose: () => void
}

/**
 * For debugging the chat flow: the session's saved state (`chat_state_id`, its block,
 * `chat_state_data`) and what happened inside the latest message's turn (from the send response).
 */
export function SandboxDebugPanel({ session, onClose }: SandboxDebugPanelProps) {
  const { data: chatConfig } = useChatConfiguration()
  const debug = useSandboxTurnDebug(session.id)
  // Same rule as the backend: the id's type must match too ("2" is not block 2).
  const block = chatConfig?.config_json.find((b) => b.id === session.chat_state_id)

  return (
    <aside className="flex max-h-[60svh] min-h-0 w-full shrink-0 flex-col border-t md:max-h-none md:w-96 md:border-t-0 md:border-l">
      <header className="flex items-center justify-between gap-2 border-b px-3 py-2.5">
        <h2 className="flex items-center gap-2 text-sm font-semibold">
          <Bug className="size-4" /> Debug
        </h2>
        <Button variant="ghost" size="icon" aria-label="Close the debug panel" onClick={onClose}>
          <X />
        </Button>
      </header>

      <div className="grid flex-1 grid-cols-[minmax(0,1fr)] content-start gap-5 overflow-x-hidden overflow-y-auto p-3 text-xs">
        <Section title="Saved state" hint="ChatSession, as last fetched">
          <KeyValue label="chat_state_id" value={JSON.stringify(session.chat_state_id)} mono />
          <KeyValue
            label="Block"
            value={block ? blockLabel(block.block_type) : 'Not in the workflow: the next message starts at the Start block'}
          />
          {block && <Json value={block} />}
          <p className="text-muted-foreground mt-1">chat_state_data</p>
          <Json value={session.chat_state_data} />
        </Section>

        <Section title="Latest turn" hint="From the last reply; not stored, so cleared on reload">
          {debug ? (
            <>
              <KeyValue
                label="State"
                value={`${JSON.stringify(debug.before.chat_state_id)} → ${JSON.stringify(debug.after.chat_state_id)}`}
                mono
              />
              {debug.finished.length > 0 && <KeyValue label="Completed" value={debug.finished.join(', ')} />}
              {debug.order_id !== null && <KeyValue label="Order" value={`#${debug.order_id}`} mono />}
              <KeyValue label="Stopped" value={debug.stop_reason} />

              <p className="text-muted-foreground mt-1">
                Extraction steps ({debug.steps.length} LLM call{debug.steps.length === 1 ? '' : 's'})
              </p>
              {debug.steps.length === 0 ? (
                <p className="text-muted-foreground italic">None</p>
              ) : (
                <ol className="grid gap-2">
                  {debug.steps.map((step, index) => (
                    <StepCard key={index} index={index} step={step} />
                  ))}
                </ol>
              )}

              <p className="text-muted-foreground mt-1">Reply</p>
              {debug.missing.length > 0 && <KeyValue label="Still needed" value={debug.missing.join(', ')} />}
              {debug.issues.length > 0 && <KeyValue label="Issues" value={debug.issues.join(' ')} />}
              <KeyValue
                label="Tool calls"
                value={debug.tool_calls.length ? debug.tool_calls.map((call) => call.name).join(', ') : 'none'}
                mono
              />
              <Collapsible summary="Reply system prompt">
                <Pre>{debug.reply_system_prompt}</Pre>
              </Collapsible>
            </>
          ) : (
            <p className="text-muted-foreground italic">Send a message to see what happens inside its turn.</p>
          )}
        </Section>
      </div>
    </aside>
  )
}

function StepCard({ index, step }: { index: number; step: FlowStepDebug }) {
  return (
    <li className="grid gap-1.5 rounded-md border p-2">
      <div className="flex items-center justify-between gap-2">
        <span className="font-medium">
          {index + 1}. {blockLabel(step.block_type)}{' '}
          <span className="text-muted-foreground font-mono">({JSON.stringify(step.block_id)})</span>
        </span>
        {step.go_back ? (
          <Badge variant="outline" className="border-amber-500/50 text-amber-700 dark:text-amber-400">
            <Undo2 /> Go back
          </Badge>
        ) : step.complete ? (
          <Badge variant="outline" className="border-emerald-500/50 text-emerald-700 dark:text-emerald-400">
            <CircleCheck /> Complete
          </Badge>
        ) : (
          <Badge variant="outline">
            <CircleDashed /> Not complete
          </Badge>
        )}
      </div>
      <p className="text-muted-foreground">LLM returned</p>
      <Json value={step.extracted} />
      {step.missing.length > 0 && <KeyValue label="Missing" value={step.missing.join(', ')} />}
      {step.issues.length > 0 && <KeyValue label="Issues" value={step.issues.join(' ')} />}
      <Collapsible summary="chat_state_data after this step">
        <Json value={step.chat_state_data} />
      </Collapsible>
      <Collapsible summary="Extraction system prompt">
        <Pre>{step.system_prompt}</Pre>
      </Collapsible>
    </li>
  )
}

function Section({ title, hint, children }: { title: string; hint: string; children: ReactNode }) {
  return (
    <section className="grid gap-1.5">
      <div>
        <h3 className="text-sm font-semibold">{title}</h3>
        <p className="text-muted-foreground">{hint}</p>
      </div>
      {children}
    </section>
  )
}

function KeyValue({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <p className="break-words">
      <span className="text-muted-foreground">{label}: </span>
      <span className={mono ? 'font-mono' : 'font-medium'}>{value}</span>
    </p>
  )
}

function Collapsible({ summary, children }: { summary: string; children: ReactNode }) {
  return (
    <details>
      <summary className="text-muted-foreground hover:text-foreground cursor-pointer select-none">{summary}</summary>
      <div className="mt-1">{children}</div>
    </details>
  )
}

function Json({ value }: { value: unknown }) {
  return <Pre>{JSON.stringify(value, null, 2)}</Pre>
}

function Pre({ children }: { children: string }) {
  return (
    <pre className="bg-muted overflow-x-auto rounded-md p-2 font-mono text-[11px] leading-relaxed break-words whitespace-pre-wrap">
      {children}
    </pre>
  )
}
