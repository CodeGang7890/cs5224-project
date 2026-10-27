import { Eye } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

import type { ChatSession, SentBy } from "../types";

const SENDER_PREFIX: Record<SentBy, string> = {
  customer: "",
  "business-automated": "Assistant: ",
  "business-manual": "Business: ",
};

const formatDateTime = (iso: string) =>
  new Date(iso).toLocaleString([], {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });

interface ChatSessionTableProps {
  sessions: ChatSession[];
  stepLabel: (stateId: ChatSession["chat_state_id"]) => string | null;
  onOpen: (id: number) => void;
}

/** Read-only list of chats. Clicking a row (or View) opens the conversation. */
export function ChatSessionTable({
  sessions,
  stepLabel,
  onOpen,
}: ChatSessionTableProps) {
  return (
    <div className="rounded-xl border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="pl-4">Customer</TableHead>
            <TableHead>Current step</TableHead>
            <TableHead className="text-right">Messages</TableHead>
            <TableHead className="w-[32%]">Last message</TableHead>
            <TableHead>Last chat</TableHead>
            <TableHead>Started</TableHead>
            <TableHead className="w-12">
              <span className="sr-only">Actions</span>
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {sessions.map((session) => {
            const lastMessage = session.chat_message_json.at(-1);
            const step = stepLabel(session.chat_state_id);
            return (
              <TableRow
                key={session.id}
                className="cursor-pointer"
                onClick={() => onOpen(session.id)}
              >
                <TableCell className="pl-4">
                  <div className="flex items-center gap-2">
                    <span className="font-medium">
                      {session.display_name || "Unnamed customer"}
                    </span>
                    {session.is_sandbox && (
                      <Badge
                        variant="outline"
                        className="border-amber-500/50 text-amber-700 dark:text-amber-400"
                      >
                        Sandbox
                      </Badge>
                    )}
                  </div>
                  <span className="text-muted-foreground text-xs tabular-nums">
                    {session.phone_number || "No phone number"}
                  </span>
                </TableCell>
                <TableCell>
                  {step ?? <span className="text-muted-foreground">—</span>}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {session.chat_message_json.length}
                </TableCell>
                <TableCell className="max-w-0">
                  <p
                    className="text-muted-foreground truncate"
                    title={lastMessage?.message}
                  >
                    {lastMessage
                      ? `${SENDER_PREFIX[lastMessage.sent_by]}${lastMessage.message}`
                      : "No messages yet"}
                  </p>
                </TableCell>
                <TableCell className="whitespace-nowrap tabular-nums">
                  {formatDateTime(session.last_chat_time)}
                </TableCell>
                <TableCell className="text-muted-foreground whitespace-nowrap tabular-nums">
                  {new Date(session.created_time).toLocaleDateString([], {
                    day: "numeric",
                    month: "short",
                    year: "numeric",
                  })}
                </TableCell>
                <TableCell>
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label={`View chat with ${session.display_name || session.phone_number || `#${session.id}`}`}
                    onClick={(event) => {
                      event.stopPropagation();
                      onOpen(session.id);
                    }}
                  >
                    <Eye />
                  </Button>
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
