// Route paths, top-navigation tabs and the sections' sub-tabs. Use `paths` instead of hard-coding
// URL strings.
export const paths = {
  home: '/',
  workflow: '/workflow',
  catalog: '/catalog',
  catalogProducts: '/catalog/products',
  catalogServices: '/catalog/services',
  catalogFaqs: '/catalog/faqs',
  orders: '/orders',
  productOrders: '/orders/products',
  serviceOrders: '/orders/services',
  payment: '/orders/payment',
  chats: '/chats',
  conversations: '/chats/conversations',
  questions: '/chats/questions',
  chatSandbox: '/chats/sandbox',
} as const

/** Top-nav tabs. `requiresAuth` tabs are hidden while logged out (their pages still show the login guard). */
export const navItems = [
  { to: paths.home, label: 'Home', requiresAuth: false },
  { to: paths.workflow, label: 'Workflow', requiresAuth: true },
  { to: paths.catalog, label: 'Catalog', requiresAuth: true },
  { to: paths.orders, label: 'Orders', requiresAuth: true },
  { to: paths.chats, label: 'Chats', requiresAuth: true },
] as const

export interface SubTab {
  to: string
  label: string
}

/** The sub-tabs of each section; the first is the section's default page. */
export const catalogTabs: SubTab[] = [
  { to: paths.catalogProducts, label: 'Products' },
  { to: paths.catalogServices, label: 'Services' },
  { to: paths.catalogFaqs, label: 'FAQs' },
]

export const ordersTabs: SubTab[] = [
  { to: paths.productOrders, label: 'Products' },
  { to: paths.serviceOrders, label: 'Services' },
  { to: paths.payment, label: 'Payment' },
]

export const chatsTabs: SubTab[] = [
  { to: paths.conversations, label: 'Conversations' },
  { to: paths.questions, label: 'Unanswered questions' },
  { to: paths.chatSandbox, label: 'Chat Sandbox' },
]

/** Old URLs (before the sections had sub-tabs) → where they live now. Their query strings are kept. */
export const legacyRedirects: { from: string; to: string }[] = [
  { from: '/product', to: paths.catalogProducts },
  { from: '/service', to: paths.catalogServices },
  { from: '/faq', to: paths.catalogFaqs },
  { from: '/payment', to: paths.payment },
  { from: '/chat-sandbox', to: paths.chatSandbox },
]
