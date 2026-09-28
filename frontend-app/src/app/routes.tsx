import type { RouteObject } from 'react-router'

import { RootLayout } from '@/components/layout/root-layout'
import { paths } from '@/config/navigation'
import { ChatSandboxPage } from '@/pages/chat-sandbox-page'
import { ChatsPage } from '@/pages/chats-page'
import { ErrorPage } from '@/pages/error-page'
import { FaqPage } from '@/pages/faq-page'
import { HomePage } from '@/pages/home-page'
import { NotFoundPage } from '@/pages/not-found-page'
import { PaymentPage } from '@/pages/payment-page'
import { ProductPage } from '@/pages/product-page'
import { SchedulePage } from '@/pages/schedule-page'
import { WorkflowPage } from '@/pages/workflow-page'

// All client-side routes. Add new pages here as children of the root layout,
// and add a tab in `@/config/navigation` if they belong in the top nav.
export const routes: RouteObject[] = [
  {
    path: paths.home,
    element: <RootLayout />,
    errorElement: <ErrorPage />,
    children: [
      { index: true, element: <HomePage /> },
      { path: paths.workflow, element: <WorkflowPage /> },
      { path: paths.product, element: <ProductPage /> },
      { path: paths.schedule, element: <SchedulePage /> },
      { path: paths.payment, element: <PaymentPage /> },
      { path: paths.faq, element: <FaqPage /> },
      { path: paths.chats, element: <ChatsPage /> },
      { path: paths.chatSandbox, element: <ChatSandboxPage /> },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
]
