import { MessagesSquare } from "lucide-react";

import { SectionLayout } from "@/components/layout/section-layout";
import { chatsTabs, paths } from "@/config/navigation";
import { useOpenQuestionCount } from "@/features/questions";

/** The Chats section: conversations, unanswered questions and the Chat Sandbox. */
export function ChatsPage() {
  const { data: openCount = 0 } = useOpenQuestionCount();
  return (
    <SectionLayout
      icon={MessagesSquare}
      accent="sky"
      title="Chats"
      description="Your business's conversations with customers, the questions the assistant couldn't answer, and a sandbox to try the assistant."
      tabs={chatsTabs}
      badges={{
        [paths.questions]: openCount > 0 && (
          <span
            className="bg-destructive ml-2 inline-flex min-w-5 items-center justify-center rounded-full px-1.5 text-xs font-semibold text-white tabular-nums"
            aria-label={`${openCount} need an answer`}
          >
            {openCount}
          </span>
        ),
      }}
    />
  );
}
