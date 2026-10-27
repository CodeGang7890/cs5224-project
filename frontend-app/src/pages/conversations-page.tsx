import { useNavigate } from "react-router";

import { TabPage } from "@/components/common/tab-page";
import { paths } from "@/config/navigation";
import { ChatSessionBrowser } from "@/features/chat-sessions";
import { OpenQuestionsAlert } from "@/features/questions";

export function ConversationsPage() {
  const navigate = useNavigate();
  return (
    <TabPage
      title="Conversations"
      section="Chats"
      description="Browse your business's conversations with customers."
    >
      <OpenQuestionsAlert onView={() => navigate(paths.questions)} />
      <ChatSessionBrowser />
    </TabPage>
  );
}
