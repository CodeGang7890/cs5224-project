import type { RouteObject } from 'react-router'

import { RootLayout } from '@/components/layout/root-layout'
import { paths } from '@/config/navigation'
import { RequireAuth } from '@/features/auth'
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
// Pages that need a logged-in user go inside the `<RequireAuth />` group.
export const routes: RouteObject[] = [
  {
    path: paths.home,
    element: <RootLayout />,
    errorElement: <ErrorPage />,
    children: [
      { index: true, element: <HomePage /> },
      { path: paths.schedule, element: <SchedulePage /> },
      { path: paths.payment, element: <PaymentPage /> },
      // Login required: shows a "you need to be logged in" message instead when logged out.
      {
        element: <RequireAuth />,
        children: [
          { path: paths.workflow, element: <WorkflowPage /> },
          { path: paths.product, element: <ProductPage /> },
          { path: paths.faq, element: <FaqPage /> },
          { path: paths.chatSandbox, element: <ChatSandboxPage /> },
        ],
      },
      { path: paths.chats, element: <ChatsPage /> },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
]
