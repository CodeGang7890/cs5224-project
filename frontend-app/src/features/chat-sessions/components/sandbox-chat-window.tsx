import {
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
} from "react";
import {
  Bug,
  CircleAlert,
  FlaskConical,
  MessageSquareDashed,
  Trash2,
  SendHorizontal,
} from "lucide-react";

import { ConfirmDialog } from "@/components/common/confirm-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { getFormErrors } from "@/lib/form-errors";
import type { ApiError } from "@/types/api";

import {
  useDeleteSandboxSession,
  useIsSendingSandboxMessage,
  useSendSandboxMessage,
} from "../hooks/use-chat-sessions";
import { useChatSteps } from "../hooks/use-chat-steps";
import { CHAT_MESSAGE_MAX_LENGTH, sessionLabel } from "../sandbox";
import type { ChatSession } from "../types";
import { ChatMessageBubble, TypingBubble } from "./chat-message-bubble";
import { ChatStateSummary } from "./chat-state-summary";

const SUGGESTIONS = [
  "Hi! What do you sell?",
  "Are you open today?",
  "I'd like to place an order.",
];

interface SandboxChatWindowProps {
  session: ChatSession;
  businessName: string;
  /** Unsent text, kept by the parent so each chat keeps its own draft. */
  draft: string;
  onDraftChange: (draft: string) => void;
  onDeleted: () => void;
  /** Whether the debug panel (chat flow state) is open next to the chat. */
  debugOpen: boolean;
  onDebugOpenChange: (open: boolean) => void;
}

/** One sandbox chat: the conversation, the message box and a delete button. */
export function SandboxChatWindow({
  session,
  businessName,
  draft,
  onDraftChange,
  onDeleted,
  debugOpen,
  onDebugOpenChange,
}: SandboxChatWindowProps) {
  const send = useSendSandboxMessage(session.id);
  const isSending = useIsSendingSandboxMessage(session.id);
  const remove = useDeleteSandboxSession();
  const { stepLabel } = useChatSteps();
  const [deleteOpen, setDeleteOpen] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);
  const messages = session.chat_message_json;
  const label = sessionLabel(session);

  // Keep the newest message (or the typing indicator) in view.
  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [session.id, messages.length, isSending]);

  const sendMessage = (text: string) => {
    const message = text.trim();
    if (!message || isSending) return;
    onDraftChange("");
    send.mutate(message);
  };

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    sendMessage(draft);
  };

  // Enter sends; Shift+Enter adds a new line (and Enter while composing, e.g. IME input, doesn't send).
  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (
      event.key === "Enter" &&
      !event.shiftKey &&
      !event.nativeEvent.isComposing
    ) {
      event.preventDefault();
      sendMessage(draft);
    }
  };

  const onConfirmDelete = () => {
    remove.mutate(session.id, {
      onSuccess: () => {
        setDeleteOpen(false);
        onDeleted();
      },
    });
  };

  const tooLong = draft.length > CHAT_MESSAGE_MAX_LENGTH;
  const canSend = draft.trim() !== "" && !tooLong && !isSending;

  return (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col">
      <header className="flex items-center gap-3 border-b px-4 py-3">
        <div className="flex size-10 shrink-0 items-center justify-center rounded-full bg-amber-500/15 text-amber-600 dark:text-amber-400">
          <FlaskConical className="size-5" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold">{label}</p>
          <p className="text-muted-foreground truncate text-xs">
            Chatting with {businessName} as a pretend customer
            {session.phone_number && ` (${session.phone_number})`} · started{" "}
            {new Date(session.created_time).toLocaleDateString()}
          </p>
        </div>
        <Button
          variant={debugOpen ? "secondary" : "ghost"}
          size="icon"
          aria-label="Debug: show the chat flow state"
          aria-pressed={debugOpen}
          title="Debug: show the chat flow state"
          onClick={() => onDebugOpenChange(!debugOpen)}
        >
          <Bug />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          aria-label={`Delete ${label}`}
          title="Delete this sandbox chat"
          disabled={isSending}
          onClick={() => {
            remove.reset();
            setDeleteOpen(true);
          }}
        >
          <Trash2 className="text-destructive" />
        </Button>
      </header>

      {/* Where the chat flow is, and what it has collected (updated after each reply). */}
      <div className="bg-muted/30 flex flex-wrap items-center gap-x-4 gap-y-1 border-b px-4 py-2 text-xs">
        <span className="flex items-center gap-1.5">
          <span className="text-muted-foreground">Step</span>
          <Badge variant="secondary">
            {stepLabel(session.chat_state_id) ?? "—"}
          </Badge>
        </span>
        <ChatStateSummary data={session.chat_state_data} />
      </div>

      <div className="bg-muted/20 flex-1 overflow-y-auto px-4 py-4">
        {messages.length === 0 && !isSending ? (
          <div className="flex h-full flex-col items-center justify-center gap-3 text-center">
            <MessageSquareDashed className="text-muted-foreground size-10" />
            <p className="font-medium">Start the conversation</p>
            <p className="text-muted-foreground max-w-sm text-sm">
              Send a message as if you were a customer, and see how your
              assistant replies.
            </p>
            <div className="flex flex-wrap justify-center gap-2">
              {SUGGESTIONS.map((suggestion) => (
                <Button
                  key={suggestion}
                  variant="outline"
                  size="sm"
                  onClick={() => sendMessage(suggestion)}
                >
                  {suggestion}
                </Button>
              ))}
            </div>
          </div>
        ) : (
          <ul className="flex flex-col gap-3" aria-live="polite">
            {messages.map((message, index) => (
              <ChatMessageBubble
                key={`${index}-${message.message_time}`}
                message={message}
              />
            ))}
            {isSending && <TypingBubble />}
          </ul>
        )}
        <div ref={endRef} />
      </div>

      {send.error && !isSending && <SendError error={send.error} />}

      <form onSubmit={onSubmit} className="flex items-end gap-2 border-t p-3">
        <div className="grid flex-1 gap-1">
          <Textarea
            value={draft}
            onChange={(event) => onDraftChange(event.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Type a message as the customer…"
            aria-label="Message"
            aria-invalid={tooLong || undefined}
            rows={1}
            className="max-h-40 min-h-10 resize-none"
          />
          {draft.length > CHAT_MESSAGE_MAX_LENGTH - 500 && (
            <p
              className={`text-right text-xs ${tooLong ? "text-destructive" : "text-muted-foreground"}`}
            >
              {draft.length} / {CHAT_MESSAGE_MAX_LENGTH}
            </p>
          )}
        </div>
        <Button
          type="submit"
          size="icon"
          className="size-10"
          disabled={!canSend}
          aria-label="Send message"
        >
          <SendHorizontal />
        </Button>
      </form>

      <ConfirmDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        title="Delete this sandbox chat?"
        description={
          <span className="grid gap-2">
            <span>
              “{label}” and its {messages.length} message
              {messages.length === 1 ? "" : "s"} will be deleted. This can't be
              undone.
            </span>
            {remove.error && (
              <span role="alert" className="text-destructive">
                Couldn't delete it: {remove.error.message}
              </span>
            )}
          </span>
        }
        confirmLabel="Delete"
        pendingLabel="Deleting…"
        destructive
        isPending={remove.isPending}
        onConfirm={onConfirmDelete}
      />
    </div>
  );
}

function SendError({ error }: { error: ApiError }) {
  const { fields, form } = getFormErrors(error);
  const detail = Object.values(fields).join(" ") || form || error.message;
  // 5xx: the LLM failed, but the backend already saved the message.
  const isLlmError = error.status !== undefined && error.status >= 500;
  return (
    <p
      role="alert"
      className="text-destructive flex items-start gap-2 border-t px-4 py-2 text-sm"
    >
      <CircleAlert className="mt-0.5 size-4 shrink-0" />
      <span>
        {isLlmError
          ? "The assistant couldn't reply: "
          : "Couldn't send your message: "}
        {detail}
        {isLlmError && " Your message was still saved."}
      </span>
    </p>
  );
}
