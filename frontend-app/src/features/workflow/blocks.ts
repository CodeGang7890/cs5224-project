import { CircleCheck, ClipboardList, MessageSquareText, Play, ShoppingBag, type LucideIcon } from 'lucide-react'

import type { BlockType } from './types'

interface BlockMeta {
  label: string
  description: string
  icon: LucideIcon
  /** Coloured strip along the top of the block. */
  accentClassName: string
  /** Icon tile colours. */
  iconClassName: string
}

/** How each block type looks in the workflow editor. */
export const BLOCK_META: Record<BlockType, BlockMeta> = {
  START_BLOCK: {
    label: 'Start',
    description: 'Where every chat begins.',
    icon: Play,
    accentClassName: 'border-t-emerald-500',
    iconClassName: 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400',
  },
  PRODUCT_SELECTION_BLOCK: {
    label: 'Product selection',
    description: 'The customer picks a product.',
    icon: ShoppingBag,
    accentClassName: 'border-t-sky-500',
    iconClassName: 'bg-sky-500/15 text-sky-600 dark:text-sky-400',
  },
  DETAILS_COLLECTION_BLOCK: {
    label: 'Details collection',
    description: "Collect the customer's details.",
    icon: ClipboardList,
    accentClassName: 'border-t-amber-500',
    iconClassName: 'bg-amber-500/15 text-amber-600 dark:text-amber-400',
  },
  CONFIRMATION_BLOCK: {
    label: 'Confirmation',
    description: 'Confirm the order with the customer.',
    icon: CircleCheck,
    accentClassName: 'border-t-violet-500',
    iconClassName: 'bg-violet-500/15 text-violet-600 dark:text-violet-400',
  },
  SEND_MESSAGE_BLOCK: {
    label: 'Send message',
    description: 'Sends your message, then moves on.',
    icon: MessageSquareText,
    accentClassName: 'border-t-rose-500',
    iconClassName: 'bg-rose-500/15 text-rose-600 dark:text-rose-400',
  },
}

/** Longest Send message text (configuration-service `CHAT_MESSAGE_MAX_LENGTH`, WhatsApp's limit). */
export const SEND_MESSAGE_MAX_LENGTH = 4096

/** What a new Send message block says until the business edits it. */
export const DEFAULT_SEND_MESSAGE = 'Thank you! We have received your message.'

/** Block size on the canvas (the node is `w-56`); used to centre dropped blocks on the cursor. */
export const BLOCK_WIDTH = 224
export const BLOCK_HEIGHT = 76
