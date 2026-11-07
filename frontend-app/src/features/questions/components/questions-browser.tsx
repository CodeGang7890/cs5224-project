import { useEffect, useState } from "react";
import { useSearchParams } from "react-router";
import { CircleHelp } from "lucide-react";

import { ConfirmDialog } from "@/components/common/confirm-dialog";
import { PaginationControls } from "@/components/common/pagination-controls";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { Skeleton } from "@/components/ui/skeleton";
import { usePageParam } from "@/hooks/use-page-param";
import { cn } from "@/lib/utils";

import {
  QUESTIONS_PAGE_SIZE,
  useDismissQuestion,
  useQuestions,
} from "../hooks/use-questions";
import {
  QUESTION_STATUSES,
  type QuestionStatus,
  type UnansweredQuestion,
} from "../types";
import { AnswerQuestionDialog } from "./answer-question-dialog";

type StatusFilter = QuestionStatus | "all";
const DEFAULT_STATUS: StatusFilter = "open";

const STATUS_META: Record<
  QuestionStatus,
  { label: string; className: string }
> = {
  open: {
    label: "Needs answer",
    className:
      "border-amber-500/50 bg-amber-500/10 text-amber-700 dark:text-amber-400",
  },
  answered: {
    label: "Answered",
    className:
      "border-emerald-500/50 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400",
  },
  dismissed: { label: "Dismissed", className: "text-muted-foreground" },
};

const STATUS_OPTIONS: { value: StatusFilter; label: string }[] = [
  { value: "open", label: "Needs answer" },
  { value: "answered", label: "Answered" },
  { value: "dismissed", label: "Dismissed" },
  { value: "all", label: "All questions" },
];

/** The status filter, kept in the URL (`?status=`; "open" is the default and left out). */
function useStatusParam() {
  const [searchParams, setSearchParams] = useSearchParams();
  const raw = searchParams.get("status");
  const value: StatusFilter =
    raw === "all" || QUESTION_STATUSES.includes(raw as QuestionStatus)
      ? (raw as StatusFilter)
      : DEFAULT_STATUS;
  const setValue = (next: StatusFilter) =>
    setSearchParams(
      (params) => {
        if (next === DEFAULT_STATUS) params.delete("status");
        else params.set("status", next);
        params.delete("page");
        return params;
      },
      { replace: true },
    );
  return [value, setValue] as const;
}

/** The Chats tab's "Unanswered questions" sub-tab: questions the assistant asked the team, to answer or dismiss. */
export function QuestionsBrowser() {
  const [statusFilter, setStatusFilter] = useStatusParam();
  const [page, setPage] = usePageParam();
  const { data, isPending, isError, error, refetch, isPlaceholderData } =
    useQuestions({
      status: statusFilter === "all" ? undefined : statusFilter,
      page,
      page_size: QUESTIONS_PAGE_SIZE,
    });
  const [answering, setAnswering] = useState<UnansweredQuestion>();
  const [dismissing, setDismissing] = useState<UnansweredQuestion>();
  const [actionError, setActionError] = useState<string | null>(null);
  const dismissQuestion = useDismissQuestion();

  // A page past the end (e.g. after answering the last question on it): go back one.
  useEffect(() => {
    if (isError && error.status === 404 && page > 1) setPage(page - 1);
  }, [isError, error, page, setPage]);

  const handleDismiss = () => {
    if (!dismissing) return;
    dismissQuestion.mutate(dismissing.id, {
      onSuccess: () => setDismissing(undefined),
      onError: (err) => {
        setDismissing(undefined);
        setActionError(err.message);
      },
    });
  };

  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-end gap-3 rounded-xl border p-3">
        <div className="grid gap-1.5">
          <Label
            htmlFor="question-status"
            className="text-muted-foreground text-xs font-normal"
          >
            Show
          </Label>
          <NativeSelect
            id="question-status"
            className="w-48"
            value={statusFilter}
            onChange={(event) =>
              setStatusFilter(event.target.value as StatusFilter)
            }
          >
            {STATUS_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </NativeSelect>
        </div>
        <p className="text-muted-foreground max-w-xl text-xs">
          When a customer asks something your FAQs and product details don't
          cover, the assistant tells them the team will reply, and the question
          appears here. Your answer is sent in their chat and saved to your
          FAQs.
        </p>
      </div>

      {actionError && (
        <p role="alert" className="text-destructive text-sm">
          {actionError}
        </p>
      )}

      {isPending ? (
        <div
          className="grid gap-2"
          aria-busy="true"
          aria-label="Loading questions"
        >
          {Array.from({ length: 4 }, (_, i) => (
            <Skeleton key={i} className="h-20 w-full" />
          ))}
        </div>
      ) : isError && !data ? (
        <div className="flex flex-col items-start gap-3 rounded-lg border border-destructive/50 p-4">
          <p className="text-destructive text-sm">
            {error.status === 403
              ? "Your account is not linked to a business, so there are no questions to show."
              : `Couldn't load questions: ${error.message}`}
          </p>
          <Button variant="outline" size="sm" onClick={() => refetch()}>
            Try again
          </Button>
        </div>
      ) : data.results.length === 0 ? (
        <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed p-10 text-center">
          <CircleHelp className="text-muted-foreground size-10" />
          <p className="font-medium">
            {statusFilter === "open"
              ? "No questions need your answer"
              : "No questions here"}
          </p>
          <p className="text-muted-foreground text-sm">
            {statusFilter === "open"
              ? "You're all caught up. New questions appear here when the assistant can't answer a customer."
              : "Try another filter."}
          </p>
        </div>
      ) : (
        <div
          className={cn(
            "grid gap-3",
            isPlaceholderData && "opacity-60 transition-opacity",
          )}
        >
          <ul className="grid gap-3">
            {data.results.map((item) => (
              <QuestionCard
                key={item.id}
                item={item}
                onAnswer={() => {
                  setActionError(null);
                  setAnswering(item);
                }}
                onDismiss={() => {
                  setActionError(null);
                  setDismissing(item);
                }}
              />
            ))}
          </ul>
          <PaginationControls
            page={page}
            pageSize={QUESTIONS_PAGE_SIZE}
            count={data.count}
            onPageChange={setPage}
            disabled={isPlaceholderData}
          />
        </div>
      )}

      <AnswerQuestionDialog
        question={answering}
        onClose={() => setAnswering(undefined)}
      />
      <ConfirmDialog
        open={dismissing !== undefined}
        onOpenChange={(open) => !open && setDismissing(undefined)}
        title="Dismiss this question?"
        description={
          <>
            “{dismissing?.question}” will be closed without a reply. The
            customer won't get an answer, and nothing is added to your FAQs.
          </>
        }
        confirmLabel="Dismiss"
        pendingLabel="Dismissing…"
        destructive
        isPending={dismissQuestion.isPending}
        onConfirm={handleDismiss}
      />
    </div>
  );
}

function QuestionCard({
  item,
  onAnswer,
  onDismiss,
}: {
  item: UnansweredQuestion;
  onAnswer: () => void;
  onDismiss: () => void;
}) {
  const meta = STATUS_META[item.status];
  return (
    <li className="grid gap-3 rounded-xl border p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="grid min-w-0 gap-1">
          <p className="font-medium break-words">{item.question}</p>
          <p className="text-muted-foreground flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
            <span>{item.display_name || "Unnamed customer"}</span>
            {item.phone_number && <span>· {item.phone_number}</span>}
            <span>· asked {new Date(item.created_time).toLocaleString()}</span>
            {item.is_sandbox && (
              <Badge
                variant="outline"
                className="border-amber-500/50 text-amber-700 dark:text-amber-400"
              >
                Sandbox
              </Badge>
            )}
          </p>
        </div>
        <Badge variant="outline" className={meta.className}>
          {meta.label}
        </Badge>
      </div>

      {item.status === "answered" && (
        <div className="grid gap-1 rounded-md bg-muted/40 p-3 text-sm">
          <p className="whitespace-pre-wrap break-words">
            {item.answer ?? "The FAQ for this answer was deleted."}
          </p>
          <p className="text-muted-foreground text-xs">
            Answered{" "}
            {item.answered_time &&
              new Date(item.answered_time).toLocaleString()}
            {item.faq !== null &&
              " · saved to your FAQs (edit it in Catalog → FAQs)"}
          </p>
        </div>
      )}

      {item.status === "open" && (
        <div className="flex flex-wrap gap-2">
          <Button size="sm" onClick={onAnswer}>
            Answer
          </Button>
          <Button size="sm" variant="ghost" onClick={onDismiss}>
            Dismiss
          </Button>
        </div>
      )}
    </li>
  );
}
