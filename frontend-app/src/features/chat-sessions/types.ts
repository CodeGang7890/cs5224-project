import type { ChatStep } from "@/features/workflow";

/** Who sent a message, mirrored from configuration-service `chat_app/constants.py`. */
export type SentBy = "customer" | "business-manual" | "business-automated";

/** One message of `ChatSession.chat_message_json`. */
export interface ChatMessage {
  message: string;
  sent_by: SentBy;
  /** ISO 8601 with a timezone. */
  message_time: string;
}

/** A product the customer chose; `name` and `unit_price` are a snapshot from when it was chosen. */
export interface ChatStateItem {
  product_id: number;
  name: string;
  /** Decimal string, e.g. "5.50". */
  unit_price: string;
  quantity: number;
}

/** `ChatSession.chat_state_data`: what the order steps have collected so far. Every key is optional. */
export interface ChatStateData {
  items?: ChatStateItem[];
  /** True once the customer said the items are everything they want (cleared when they change). */
  items_confirmed?: boolean;
  /** Collected customer details by field key (the Details collection step's fields), e.g. `postal_code`. */
  details?: Record<string, string | number>;
  /** The last order (Orders tab) placed in this chat; once placed, the chat goes back to the start. */
  last_order_id?: number;
  /** The service chosen for a booking (a snapshot). */
  service?: {
    service_id: number;
    name: string;
    price: string;
    duration_minutes: number;
    buffer_minutes: number;
  };
  /** The start time chosen for the booking (ISO 8601). */
  slot?: string;
  /** The free start times offered to the customer, numbered from 1 in this order (ISO 8601). */
  slot_options?: string[];
  /** The last booking (Orders tab → Services) made in this chat. */
  last_booking_id?: number;
}

/** A conversation between a business and one customer, or a sandbox (test) chat. */
export interface ChatSession {
  id: number;
  business: number;
  /** Empty for sandbox sessions without a mock number. */
  phone_number: string;
  display_name: string;
  created_time: string;
  last_chat_time: string;
  /** Oldest message first. */
  chat_message_json: ChatMessage[];
  /** The chat flow step the customer is at: `start` (no order in progress) or an order step. */
  chat_state_id: ChatStep;
  chat_state_data: ChatStateData;
  /** A test chat from the Chat Sandbox rather than a real customer. */
  is_sandbox: boolean;
}

/** One order step's extraction + deterministic check in a turn of the backend's chat flow. */
export interface FlowStepDebug {
  step: ChatStep;
  /** The extraction system prompt sent to the LLM. */
  system_prompt: string;
  /** The LLM's JSON answer, before the checks. */
  extracted: Record<string, unknown>;
  complete: boolean;
  go_back: boolean;
  /** The earlier step the customer went back to from this step (the LLM's `go_back_to`), or null. */
  go_back_to: string | null;
  missing: string[];
  issues: string[];
  /** `chat_state_data` after this step's check. */
  chat_state_data: ChatStateData;
}

/** What happened inside one sandbox message's turn (not stored; only in the send response). */
export interface SandboxTurnDebug {
  before: {
    chat_state_id: ChatSession["chat_state_id"];
    chat_state_data: ChatStateData;
  };
  after: {
    chat_state_id: ChatSession["chat_state_id"];
    chat_state_data: ChatStateData;
  };
  /** The router: what the message is about, which decides the handlers that ran. */
  route: RouteDebug;
  steps: FlowStepDebug[];
  stop_reason: string;
  finished: string[];
  /** Confirmation's substage after the turn (null: not at Confirmation). `confirmed`: the order is saved. */
  confirmation: "not_confirmed" | "confirmed" | null;
  /** The order placed in this turn, or null. */
  order_id: number | null;
  /** The booking placed in this turn, or null. */
  booking_id: number | null;
  missing: string[];
  issues: string[];
  /** How the reply was made: by the LLM, or a fixed template. */
  reply_kind:
    | "llm"
    | "order_status"
    | "order_status_fallback"
    | "order_status_not_found"
    | "welcome"
    | "confirmation_request"
    | "order_confirmed"
    | "slot_options"
    | "booking_confirmation_request"
    | "booking_confirmed";
  /** The LLM reply's prompt; for a Confirmation template, the prompt of its short aside (empty if none). */
  reply_system_prompt: string;
  /** How many times the turn ran (more than 1: the chat changed while it was worked out, so it ran again). */
  attempts: number;
  tool_calls: { name: string; arguments: Record<string, unknown> }[];
  /** The question check (FAQs): does the business's information answer the question? Null unless the router found one. */
  question_check: QuestionCheckDebug | null;
  /** The order status branch: what was asked, and what the records say. Null unless the router found an order status request. */
  order_status: OrderStatusDebug | null;
  /** The welcome message sent first this turn (a chat's first message), or null. */
  welcome_message: string | null;
}

/** Mirrored from messaging-service `app/chat_flow/flow.py` `check_order_status` / `past_orders.Lookup`. */
export interface OrderStatusDebug {
  /** The extraction LLM's JSON: `{kind, numbers}`. */
  extracted: Record<string, unknown>;
  system_prompt: string;
  /** The records the reply was written from (the only facts it may use). */
  records: string;
  found: {
    kind: "order" | "booking" | "any";
    numbers: number[];
    orders: { number: number; status: string }[];
    bookings: { number: number; status: string }[];
    not_found: string[];
  };
}

/** The router's intents, mirrored from configuration-service `chat_app/constants.py` `INTENTS`. */
export type Intent =
  "order" | "booking" | "question" | "order_status" | "off_topic";

export interface RouteDebug {
  intents: Intent[];
  /** The LLM's JSON, before unknown intents were dropped. */
  extracted: Record<string, unknown>;
  system_prompt: string;
}

export interface QuestionCheckDebug {
  /** none (no question after all) · answered (from the FAQs / products) · unanswered (asked to the team). */
  kind: "none" | "answered" | "unanswered";
  question: string | null;
  /** For "unanswered": "asked" (saved for the business), "already_asked" or "too_many_questions". */
  saved: string | null;
  system_prompt: string;
}

/** Response of POST /api/chat/sandbox-sessions/{id}/messages/: the reply, plus debug info. */
export interface SandboxMessageReply extends ChatMessage {
  /** Every message the assistant sent this turn, oldest first: the welcome message (on a chat's first message, if the business has one), then the reply. */
  messages: ChatMessage[];
  debug: SandboxTurnDebug;
}

/** Body of POST /api/chat/sandbox-sessions/ (both optional); the backend sets everything else. */
export type SandboxChatSessionInput = Partial<
  Pick<ChatSession, "display_name" | "phone_number">
>;

/** Which sessions to list: real customer chats (default), both, or sandbox chats only. */
export type SandboxFilter = "exclude" | "include" | "only";

/** Sort options of GET /api/chat/sessions/ (`ordering`). */
export type ChatSessionOrdering =
  | "-last_chat_time"
  | "last_chat_time"
  | "-created_time"
  | "created_time"
  | "display_name"
  | "-display_name"
  | "phone_number";

/** Query parameters of GET /api/chat/sessions/ (all optional except paging and sorting). */
export interface ChatSessionListParams {
  page: number;
  page_size: number;
  ordering: ChatSessionOrdering;
  sandbox: SandboxFilter;
  search?: string;
  chat_state_id?: string;
  has_messages?: "true" | "false";
  /** ISO 8601 date-times (inclusive). */
  last_chat_time_after?: string;
  last_chat_time_before?: string;
  created_time_after?: string;
  created_time_before?: string;
}
