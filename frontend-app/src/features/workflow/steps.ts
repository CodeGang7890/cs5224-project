import {
  CalendarCheck,
  CalendarClock,
  CircleCheck,
  ClipboardList,
  ClipboardPen,
  Clock,
  MessageCircleQuestion,
  MessagesSquare,
  Route,
  ShoppingBag,
  Truck,
  type LucideIcon,
} from "lucide-react";

import { paths } from "@/config/navigation";

import type { ChatStep } from "./types";

/** What to call each chat step (`ChatSession.chat_state_id`), like the backend's `STEP_LABELS`. */
export const CHAT_STEP_LABELS: Record<ChatStep, string> = {
  start: "Start",
  product_selection: "Product selection",
  details_collection: "Details collection",
  confirmation: "Confirmation",
  service_selection: "Service selection",
  slot_selection: "Time slot",
  booking_details: "Booking details",
  booking_confirmation: "Booking confirmation",
};

/** The blocks of the (fixed) chat flow diagram on the Workflow tab. */
export const FLOW_NODES = [
  "settings",
  "router",
  "product_selection",
  "details_collection",
  "confirmation",
  "service_selection",
  "slot_selection",
  "booking_details",
  "booking_confirmation",
  "faqs",
  "order_status",
] as const;

/** The details blocks: Details collection (product orders) and Booking details (bookings), each with its own list. */
export const DETAILS_NODES: readonly FlowNodeId[] = [
  "details_collection",
  "booking_details",
];

export type FlowNodeId = (typeof FLOW_NODES)[number];

interface FlowNodeMeta {
  label: string;
  /** One line on the block. */
  description: string;
  /** What the block does, in its info dialog. */
  about: string;
  /** Where its data is managed, if elsewhere in the app. */
  link?: { to: string; label: string };
  /** Shown as a badge on the block, e.g. "Coming soon". */
  badge?: string;
  icon: LucideIcon;
  /** Coloured strip along the top of the block. */
  accentClassName: string;
  /** Icon tile colours. */
  iconClassName: string;
}

/** How each block of the flow diagram looks, and what it does. */
export const FLOW_NODE_META: Record<FlowNodeId, FlowNodeMeta> = {
  settings: {
    label: "Welcome & style",
    description: "The welcome message, and how the assistant writes.",
    about: "",
    icon: MessagesSquare,
    accentClassName: "border-t-violet-500",
    iconClassName: "bg-violet-500/15 text-violet-600 dark:text-violet-400",
  },
  router: {
    label: "Router",
    description: "Reads each customer message and decides what it is about.",
    about:
      "Every customer message starts here. The assistant decides what the message is about: ordering " +
      "products, booking a service, a question about your business, a past order, or something off topic. " +
      'One message can be about several things (for example "2 roses please, and do you deliver?"), and each ' +
      "part goes to its own branch. Once an order or a booking has started, its steps keep going until the " +
      "customer confirms it, or cancels it. Asking to book during an order (or to order during a booking) " +
      "switches over if nothing has been chosen yet; otherwise the assistant asks them to finish or cancel first.",
    icon: Route,
    accentClassName: "border-t-emerald-500",
    iconClassName: "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400",
  },
  product_selection: {
    label: "Product selection",
    description: "The customer picks products and quantities.",
    about:
      "The customer chooses what to order. Only your active products that are in stock can be ordered, up to " +
      "the quantity available. The assistant recaps the order and asks whether that is everything before moving on.",
    link: { to: paths.catalogProducts, label: "Manage products" },
    icon: ShoppingBag,
    accentClassName: "border-t-sky-500",
    iconClassName: "bg-sky-500/15 text-sky-600 dark:text-sky-400",
  },
  details_collection: {
    label: "Details collection",
    description: "Collects the customer's details.",
    about: "",
    icon: ClipboardList,
    accentClassName: "border-t-amber-500",
    iconClassName: "bg-amber-500/15 text-amber-600 dark:text-amber-400",
  },
  confirmation: {
    label: "Confirmation",
    description: "The customer confirms the order.",
    about:
      "The assistant shows the order summary (items, total and details) and asks the customer to reply YES. " +
      "Confirming places the order: it appears in the Orders tab, with its stock reserved. Until then, the " +
      "customer can go back and change their products or details.",
    link: { to: paths.productOrders, label: "View orders" },
    icon: CircleCheck,
    accentClassName: "border-t-violet-500",
    iconClassName: "bg-violet-500/15 text-violet-600 dark:text-violet-400",
  },
  service_selection: {
    label: "Service selection",
    description: "The customer picks a service to book.",
    about:
      "The customer chooses one of your active services that someone can do (it has at least one weekly " +
      "availability). Changing the service later drops the time chosen, since the times depend on it.",
    link: { to: paths.catalogServices, label: "Manage services" },
    icon: CalendarClock,
    accentClassName: "border-t-teal-500",
    iconClassName: "bg-teal-500/15 text-teal-600 dark:text-teal-400",
  },
  slot_selection: {
    label: "Time slot",
    description: "The customer picks a free time.",
    about:
      "The assistant offers free times, worked out from your service providers' schedules " +
      "(never made up by the AI), numbered so the customer can reply with a number, or ask for another day, " +
      "time or part of the day. A time is free if a provider who does the service has the whole duration " +
      "available and nothing booked in the buffer after it. Once booked, the time goes on hold until paid.",
    link: { to: paths.catalogServices, label: "Edit schedules" },
    icon: Clock,
    accentClassName: "border-t-cyan-500",
    iconClassName: "bg-cyan-500/15 text-cyan-600 dark:text-cyan-400",
  },
  booking_details: {
    label: "Booking details",
    description: "Collects the customer's details (the same as for orders).",
    about: "",
    icon: ClipboardPen,
    accentClassName: "border-t-amber-500",
    iconClassName: "bg-amber-500/15 text-amber-600 dark:text-amber-400",
  },
  booking_confirmation: {
    label: "Booking confirmation",
    description: "The customer confirms the booking.",
    about:
      "The assistant shows the booking summary (service, time, price and details) and asks the customer to " +
      "reply CONFIRM. Confirming saves the booking first (in the Orders tab, under Services), then tells the " +
      "customer; if someone else took that time in the meantime, they choose another.",
    link: { to: paths.serviceOrders, label: "View bookings" },
    icon: CalendarCheck,
    accentClassName: "border-t-violet-500",
    iconClassName: "bg-violet-500/15 text-violet-600 dark:text-violet-400",
  },
  faqs: {
    label: "FAQs",
    description: "Answers questions from your FAQs and products.",
    about:
      "Questions are answered only from your FAQs and product information. If they do not answer a question, " +
      "the assistant tells the customer it will check, and the question appears in Chats → Unanswered " +
      "questions. Answering it there replies in the chat and saves it as an FAQ.",
    link: { to: paths.catalogFaqs, label: "Manage FAQs" },
    icon: MessageCircleQuestion,
    accentClassName: "border-t-rose-500",
    iconClassName: "bg-rose-500/15 text-rose-600 dark:text-rose-400",
  },
  order_status: {
    label: "Order status",
    description: "The customer's past orders and bookings, and their status.",
    about:
      "Customers can ask about the orders and bookings they made before (from the same phone number). " +
      "The assistant only works out what they ask about; the system then looks it up among that " +
      "customer's own orders and bookings (anyone else's are simply not found), and the reply may only " +
      "repeat what was found, with each status (payment pending, payment received or completed). A reply " +
      "that says anything else is replaced by a plain one written by the system. It cannot change or cancel anything.",
    link: { to: paths.productOrders, label: "View orders" },
    icon: Truck,
    accentClassName: "border-t-slate-400",
    iconClassName: "bg-slate-500/15 text-slate-600 dark:text-slate-400",
  },
};
