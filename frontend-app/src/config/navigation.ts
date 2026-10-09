// Route paths and top-navigation tabs. Use `paths` instead of hard-coding URL strings.
export const paths = {
  home: '/',
  workflow: '/workflow',
  product: '/product',
  orders: '/orders',
  service: '/service',
  payment: '/payment',
  faq: '/faq',
  chats: '/chats',
  chatSandbox: '/chat-sandbox',
} as const

export const navItems = [
  { to: paths.home, label: 'Home' },
  { to: paths.workflow, label: 'Workflow' },
  { to: paths.product, label: 'Product' },
  { to: paths.orders, label: 'Orders' },
  { to: paths.service, label: 'Service' },
  { to: paths.payment, label: 'Payment' },
  { to: paths.faq, label: 'FAQ' },
  { to: paths.chats, label: 'Chats' },
  { to: paths.chatSandbox, label: 'Chat Sandbox' },
] as const
