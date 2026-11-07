import {
  ChevronLeft,
  ChevronRight,
  CircleAlert,
  MessagesSquare,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import type { DetailedPaginated } from "@/types/api";

import {
  countActiveFilters,
  PAGE_SIZES,
  toListParams,
  useChatSessionParams,
} from "../hooks/use-chat-session-params";
import { useChatSessions } from "../hooks/use-chat-sessions";
import { useChatSteps } from "../hooks/use-chat-steps";
import type { ChatSession } from "../types";
import { ChatSessionDialog } from "./chat-session-dialog";
import { ChatSessionFilters } from "./chat-session-filters";
import { ChatSessionTable } from "./chat-session-table";

/** Chats tab: every chat of your business, read only, with search, filters, sorting and paging. */
export function ChatSessionBrowser() {
  const { values, setFilters, setPage, clearFilters, openChatId, setOpenChat } =
    useChatSessionParams();
  const { data, isPending, isError, error, refetch, isPlaceholderData } =
    useChatSessions(toListParams(values));
  const { steps, stepLabel } = useChatSteps();
  const hasFilters = countActiveFilters(values) > 0;
  const openSession = data?.results.find(
    (session) => session.id === openChatId,
  );

  return (
    <div className="grid gap-4">
      <ChatSessionFilters
        values={values}
        steps={steps}
        onChange={setFilters}
        onClear={clearFilters}
      />

      {isPending ? (
        <div className="grid gap-2" aria-busy="true" aria-label="Loading chats">
          {Array.from({ length: 6 }, (_, i) => (
            <Skeleton key={i} className="h-14 w-full" />
          ))}
        </div>
      ) : isError && !data ? (
        <ErrorState
          status={error.status}
          message={error.message}
          onRetry={refetch}
          onFirstPage={() => setPage(1)}
          onClearFilters={clearFilters}
        />
      ) : data.results.length === 0 ? (
        <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed p-10 text-center">
          <MessagesSquare className="text-muted-foreground size-10" />
          <p className="font-medium">
            {hasFilters ? "No chats match these filters" : "No chats yet"}
          </p>
          <p className="text-muted-foreground text-sm">
            {hasFilters
              ? "Try removing some filters."
              : "Customer chats appear here once customers message your business."}
          </p>
          {hasFilters && (
            <Button variant="outline" onClick={clearFilters}>
              Clear filters
            </Button>
          )}
        </div>
      ) : (
        <div
          className={cn(
            "grid gap-3",
            isPlaceholderData && "opacity-60 transition-opacity",
          )}
        >
          <ChatSessionTable
            sessions={data.results}
            stepLabel={stepLabel}
            onOpen={setOpenChat}
          />
          <PaginationBar
            data={data}
            disabled={isPlaceholderData}
            onPageChange={setPage}
            onPageSizeChange={(pageSize) => setFilters({ pageSize })}
          />
        </div>
      )}

      <ChatSessionDialog
        session={openSession}
        stepLabel={stepLabel}
        onClose={() => setOpenChat(null)}
      />
    </div>
  );
}

function PaginationBar({
  data,
  disabled,
  onPageChange,
  onPageSizeChange,
}: {
  data: DetailedPaginated<ChatSession>;
  disabled: boolean;
  onPageChange: (page: number) => void;
  onPageSizeChange: (pageSize: number) => void;
}) {
  const first = (data.current_page - 1) * data.page_size + 1;
  const last = first + data.results.length - 1;
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 text-sm">
      <div className="flex items-center gap-3">
        <span className="text-muted-foreground tabular-nums">
          {first}–{last} of {data.count} chat{data.count === 1 ? "" : "s"}
        </span>
        <div className="flex items-center gap-2">
          <Label
            htmlFor="chat-page-size"
            className="text-muted-foreground text-xs font-normal"
          >
            Per page
          </Label>
          <NativeSelect
            id="chat-page-size"
            className="w-20"
            value={data.page_size}
            onChange={(event) => onPageSizeChange(Number(event.target.value))}
          >
            {PAGE_SIZES.map((size) => (
              <option key={size} value={size}>
                {size}
              </option>
            ))}
          </NativeSelect>
        </div>
      </div>
      <div className="flex items-center gap-2">
        <Button
          variant="outline"
          size="sm"
          disabled={disabled || !data.has_previous}
          onClick={() => onPageChange(data.current_page - 1)}
        >
          <ChevronLeft /> Previous
        </Button>
        <span className="tabular-nums">
          Page {data.current_page} of {data.total_pages}
        </span>
        <Button
          variant="outline"
          size="sm"
          disabled={disabled || !data.has_next}
          onClick={() => onPageChange(data.current_page + 1)}
        >
          Next <ChevronRight />
        </Button>
      </div>
    </div>
  );
}

function ErrorState({
  status,
  message,
  onRetry,
  onFirstPage,
  onClearFilters,
}: {
  status?: number;
  message: string;
  onRetry: () => void;
  onFirstPage: () => void;
  onClearFilters: () => void;
}) {
  // 404: page past the end (e.g. from an old link); 400: invalid filter values in the URL.
  const text =
    status === 403
      ? "Your account isn't linked to a business, so there are no chats to show."
      : status === 404
        ? "That page doesn't exist any more."
        : status === 400
          ? "Some filters in the address are invalid."
          : `Couldn't load chats: ${message}`;
  return (
    <div className="border-destructive/50 flex flex-col items-start gap-3 rounded-xl border p-4">
      <p className="text-destructive flex items-center gap-2 text-sm">
        <CircleAlert className="size-4" /> {text}
      </p>
      {status === 404 ? (
        <Button variant="outline" size="sm" onClick={onFirstPage}>
          Go to the first page
        </Button>
      ) : status === 400 ? (
        <Button variant="outline" size="sm" onClick={onClearFilters}>
          Clear filters
        </Button>
      ) : (
        status !== 403 && (
          <Button variant="outline" size="sm" onClick={() => onRetry()}>
            Try again
          </Button>
        )
      )}
    </div>
  );
}
