// Mirrors configuration-service chat_app UnansweredQuestion (GET /api/chat/questions/).

export const QUESTION_STATUSES = ["open", "answered", "dismissed"] as const;
export type QuestionStatus = (typeof QUESTION_STATUSES)[number];

/** A customer question the chat assistant couldn't answer (saved by messaging-service's chat flow, `ask_business`). */
export interface UnansweredQuestion {
  id: number;
  business: number;
  chat_session: number;
  /** The customer's (chat session's) display name and phone number. */
  display_name: string;
  phone_number: string;
  /** Asked in a Chat Sandbox test chat. */
  is_sandbox: boolean;
  question: string;
  status: QuestionStatus;
  /** The FAQ the answer was saved as (editable in Catalog → FAQs). */
  faq: number | null;
  /** The linked FAQ's current answer. */
  answer: string | null;
  created_time: string;
  answered_time: string | null;
}

export interface QuestionListParams {
  status?: QuestionStatus;
  page: number;
  page_size?: number;
}

/** POST /api/chat/questions/{id}/answer/. `question` rewords it for the FAQ (optional). */
export interface AnswerQuestionInput {
  answer: string;
  question?: string;
}
