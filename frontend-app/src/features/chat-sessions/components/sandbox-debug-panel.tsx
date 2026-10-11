import type { ReactNode } from 'react'
import { Bug, CircleCheck, CircleDashed, Undo2, X } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { CHAT_STEP_LABELS } from '@/features/workflow'

import { useSandboxTurnDebug } from '../hooks/use-chat-sessions'
import type { ChatSession, FlowStepDebug, Intent, QuestionCheckDebug, SandboxTurnDebug } from '../types'

function stepLabel(step: string): string {
  return CHAT_STEP_LABELS[step as ChatSession['chat_state_id']] ?? step
}

interface SandboxDebugPanelProps {
  session: ChatSession
  onClose: () => void
}

/**
 * For debugging the chat flow: the session's saved state (`chat_state_id`, `chat_state_data`) and
 * what happened inside the latest message's turn (from the send response): the router, the order
 * steps, the question check and the reply.
 */
export function SandboxDebugPanel({ session, onClose }: SandboxDebugPanelProps) {
  const debug = useSandboxTurnDebug(session.id)

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
          <KeyValue label="Step" value={stepLabel(session.chat_state_id)} />
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
              {debug.confirmation && <KeyValue label="Confirmation" value={CONFIRMATION_LABELS[debug.confirmation]} />}
              {debug.order_id !== null && <KeyValue label="Order placed" value={`#${debug.order_id}`} mono />}
              {debug.booking_id !== null && <KeyValue label="Booking made" value={`#${debug.booking_id}`} mono />}
              <KeyValue label="Stopped" value={debug.stop_reason} />

              <p className="text-muted-foreground mt-1">Router (1 LLM call)</p>
              <KeyValue
                label="Intents"
                value={
                  debug.route.intents.length
                    ? debug.route.intents.map((intent) => INTENT_LABELS[intent]).join(', ')
                    : 'None (e.g. a greeting)'
                }
              />
              <Collapsible summary="Router prompt and LLM JSON">
                <Json value={debug.route.extracted} />
                <Pre>{debug.route.system_prompt}</Pre>
              </Collapsible>

              <p className="text-muted-foreground mt-1">
                Order steps ({debug.steps.length} LLM call{debug.steps.length === 1 ? '' : 's'})
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

              {debug.order_status && (
                <>
                  <p className="text-muted-foreground mt-1">Order status (1 LLM call to extract, then looked up by code)</p>
                  <KeyValue label="Asked about" value={JSON.stringify(debug.order_status.extracted)} />
                  <KeyValue
                    label="Found"
                    value={
                      [
                        ...debug.order_status.found.orders.map((o) => `order #${o.number} (${o.status})`),
                        ...debug.order_status.found.bookings.map((b) => `booking #${b.number} (${b.status})`),
                      ].join(', ') || 'nothing of theirs'
                    }
                  />
                  {debug.order_status.found.not_found.length > 0 && (
                    <KeyValue label="Not found" value={debug.order_status.found.not_found.join(', ')} />
                  )}
                  <Collapsible summary="Records given to the reply">
                    <Pre>{debug.order_status.records}</Pre>
                  </Collapsible>
                  <Collapsible summary="Extraction prompt">
                    <Pre>{debug.order_status.system_prompt}</Pre>
                  </Collapsible>
                </>
              )}

              {debug.question_check ? (
                <>
                  <p className="text-muted-foreground mt-1">Question check (1 LLM call)</p>
                  <KeyValue label="Kind" value={QUESTION_KIND_LABELS[debug.question_check.kind]} />
                  {debug.question_check.question && <KeyValue label="Question" value={debug.question_check.question} />}
                  {debug.question_check.saved && (
                    <KeyValue label="Unanswered question" value={QUESTION_SAVED_LABELS[debug.question_check.saved] ?? debug.question_check.saved} />
                  )}
                  <Collapsible summary="Question check prompt">
                    <Pre>{debug.question_check.system_prompt}</Pre>
                  </Collapsible>
                </>
              ) : (
                <>
                  <p className="text-muted-foreground mt-1">Question check</p>
                  <p className="text-muted-foreground italic">Not run: the router found no question.</p>
                </>
              )}

              <p className="text-muted-foreground mt-1">Reply</p>
              {debug.missing.length > 0 && <KeyValue label="Still needed" value={debug.missing.join(', ')} />}
              {debug.issues.length > 0 && <KeyValue label="Issues" value={debug.issues.join(' ')} />}
              <KeyValue
                label="Tool calls"
                value={debug.tool_calls.length ? debug.tool_calls.map((call) => call.name).join(', ') : 'none'}
                mono
              />
              <KeyValue label="Made by" value={REPLY_KIND_LABELS[debug.reply_kind]} />
              {debug.reply_system_prompt ? (
                <Collapsible summary={debug.reply_kind === 'llm' ? 'Reply system prompt' : 'Aside system prompt'}>
                  <Pre>{debug.reply_system_prompt}</Pre>
                </Collapsible>
              ) : (
                <p className="text-muted-foreground italic">No LLM call for the reply.</p>
              )}
            </>
          ) : (
            <p className="text-muted-foreground italic">Send a message to see what happens inside its turn.</p>
          )}
        </Section>
      </div>
    </aside>
  )
}

const INTENT_LABELS: Record<Intent, string> = {
  order: 'Order',
  booking: 'Booking',
  question: 'Question',
  order_status: 'Past orders / bookings',
  off_topic: 'Off topic',
}

const CONFIRMATION_LABELS: Record<NonNullable<SandboxTurnDebug['confirmation']>, string> = {
  not_confirmed: 'Not confirmed: summary sent, waiting for CONFIRM',
  confirmed: 'Confirmed: saved, then the customer was told',
}

const REPLY_KIND_LABELS: Record<SandboxTurnDebug['reply_kind'], string> = {
  llm: 'The LLM',
  order_status: 'The LLM, from the order status records only (checked: it named nothing else)',
  order_status_fallback: 'Written by code: the LLM reply named something not in the records',
  order_status_not_found: 'Written by code: nothing of theirs found (no LLM call)',
  confirmation_request: 'Template: order summary + "reply CONFIRM" (plus an LLM aside, if any)',
  order_confirmed: 'Template: order confirmed (plus an LLM aside, if any)',
  slot_options: 'Template: the free times offered, numbered (plus an LLM aside, if any)',
  booking_confirmation_request: 'Template: booking summary + "reply CONFIRM" (plus an LLM aside, if any)',
  booking_confirmed: 'Template: booking confirmed (plus an LLM aside, if any)',
}

const QUESTION_KIND_LABELS: Record<QuestionCheckDebug['kind'], string> = {
  none: 'No question about the business after all',
  answered: 'Answered from the business information',
  unanswered: 'Not in the business information: asked the team',
}

const QUESTION_SAVED_LABELS: Record<string, string> = {
  asked: 'Saved (Chats → Unanswered questions)',
  already_asked: 'Already open in this chat (not saved again)',
  too_many_questions: 'Not saved: too many open questions in this chat',
}

function StepCard({ index, step }: { index: number; step: FlowStepDebug }) {
  return (
    <li className="grid gap-1.5 rounded-md border p-2">
      <div className="flex items-center justify-between gap-2">
        <span className="font-medium">
          {index + 1}. {stepLabel(step.step)}
        </span>
        {step.go_back ? (
          <Badge variant="outline" className="border-amber-500/50 text-amber-700 dark:text-amber-400">
            <Undo2 /> {step.go_back_to ? `Went back to ${step.go_back_to}` : 'Go back'}
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
