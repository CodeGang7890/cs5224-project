import { CircleHelp } from "lucide-react";

import { Button } from "@/components/ui/button";

import { useOpenQuestionCount } from "../hooks/use-questions";

/** "N questions need your answer" banner; renders nothing when there are none. */
export function OpenQuestionsAlert({ onView }: { onView: () => void }) {
  const { data: count = 0 } = useOpenQuestionCount();
  if (count === 0) return null;
  return (
    <div
      role="alert"
      className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-amber-500/50 bg-amber-500/10 p-3 text-sm"
    >
      <span className="flex items-center gap-2">
        <CircleHelp className="size-4 text-amber-600 dark:text-amber-400" />
        {count === 1
          ? "1 customer question needs your answer: the assistant couldn’t find it in your FAQs."
          : `${count} customer questions need your answer: the assistant couldn’t find them in your FAQs.`}
      </span>
      <Button size="sm" variant="outline" onClick={onView}>
        Answer {count === 1 ? "it" : "them"}
      </Button>
    </div>
  );
}
