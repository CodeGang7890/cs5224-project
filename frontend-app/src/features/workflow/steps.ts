import {
  CircleCheck,
  ClipboardList,
  MessageCircleQuestion,
  Route,
  ShoppingBag,
  Truck,
  type LucideIcon,
} from 'lucide-react'

import { paths } from '@/config/navigation'

import type { ChatStep } from './types'

/** What to call each chat step (`ChatSession.chat_state_id`), like the backend's `STEP_LABELS`. */
export const CHAT_STEP_LABELS: Record<ChatStep, string> = {
  start: 'Start',
  product_selection: 'Product selection',
  details_collection: 'Details collection',
  confirmation: 'Confirmation',
}

/** The blocks of the (fixed) chat flow diagram on the Workflow tab. */
export const FLOW_NODES = [
  'router',
  'product_selection',
  'details_collection',
  'confirmation',
  'faqs',
  'order_status',
] as const

export type FlowNodeId = (typeof FLOW_NODES)[number]

interface FlowNodeMeta {
  label: string
  /** One line on the block. */
  description: string
  /** What the block does, in its info dialog. */
  about: string
  /** Where its data is managed, if elsewhere in the app. */
  link?: { to: string; label: string }
  /** Shown as a badge on the block, e.g. "Coming soon". */
  badge?: string
  icon: LucideIcon
  /** Coloured strip along the top of the block. */
  accentClassName: string
  /** Icon tile colours. */
  iconClassName: string
}

/** How each block of the flow diagram looks, and what it does. */
export const FLOW_NODE_META: Record<FlowNodeId, FlowNodeMeta> = {
  router: {
    label: 'Router',
    description: 'Reads each customer message and decides what it is about.',
    about:
      'Every customer message starts here. The assistant decides what the message is about: ordering, a ' +
      'question about your business, a past order, or something off topic. One message can be about several ' +
      'things (for example "2 roses please, and do you deliver?"), and each part goes to its own branch. Once ' +
      'an order has started, the order steps keep going until the customer confirms it.',
    icon: Route,
    accentClassName: 'border-t-emerald-500',
    iconClassName: 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400',
  },
  product_selection: {
    label: 'Product selection',
    description: 'The customer picks products and quantities.',
    about:
      'The customer chooses what to order. Only your active products that are in stock can be ordered, up to ' +
      'the quantity available. The assistant recaps the order and asks whether that is everything before moving on.',
    link: { to: paths.product, label: 'Manage products' },
    icon: ShoppingBag,
    accentClassName: 'border-t-sky-500',
    iconClassName: 'bg-sky-500/15 text-sky-600 dark:text-sky-400',
  },
  details_collection: {
    label: 'Details collection',
    description: "Collects the customer's details.",
    about: '',
    icon: ClipboardList,
    accentClassName: 'border-t-amber-500',
    iconClassName: 'bg-amber-500/15 text-amber-600 dark:text-amber-400',
  },
  confirmation: {
    label: 'Confirmation',
    description: 'The customer confirms the order.',
    about:
      'The assistant shows the order summary (items, total and details) and asks the customer to reply YES. ' +
      'Confirming places the order: it appears in the Orders tab, with its stock reserved. Until then, the ' +
      'customer can go back and change their products or details.',
    link: { to: paths.orders, label: 'View orders' },
    icon: CircleCheck,
    accentClassName: 'border-t-violet-500',
    iconClassName: 'bg-violet-500/15 text-violet-600 dark:text-violet-400',
  },
  faqs: {
    label: 'FAQs',
    description: 'Answers questions from your FAQs and products.',
    about:
      'Questions are answered only from your FAQs and product information. If they do not answer a question, ' +
      'the assistant tells the customer it will check, and the question appears in Chats → Unanswered ' +
      'questions. Answering it there replies in the chat and saves it as an FAQ.',
    link: { to: paths.faq, label: 'Manage FAQs' },
    icon: MessageCircleQuestion,
    accentClassName: 'border-t-rose-500',
    iconClassName: 'bg-rose-500/15 text-rose-600 dark:text-rose-400',
  },
  order_status: {
    label: 'Order status',
    description: 'Payment and delivery status of past orders.',
    about:
      'Coming soon: customers will be able to check whether a past order is paid or on its way. For now, the ' +
      'assistant tells them this is not available yet.',
    badge: 'Coming soon',
    icon: Truck,
    accentClassName: 'border-t-slate-400',
    iconClassName: 'bg-slate-500/15 text-slate-600 dark:text-slate-400',
  },
}
