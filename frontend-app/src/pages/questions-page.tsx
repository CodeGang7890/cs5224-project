import { TabPage } from "@/components/common/tab-page";
import { QuestionsBrowser } from "@/features/questions";

export function QuestionsPage() {
  return (
    <TabPage title="Unanswered questions" section="Chats">
      <QuestionsBrowser />
    </TabPage>
  );
}
