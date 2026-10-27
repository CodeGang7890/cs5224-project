import type { RouteObject } from 'react-router'

import { RedirectKeepingSearch, SectionIndexRedirect } from '@/components/common/redirects'
import { RootLayout } from '@/components/layout/root-layout'
import { legacyRedirects, paths } from '@/config/navigation'
import { RequireAuth } from '@/features/auth'
import { CatalogPage } from '@/pages/catalog-page'
import { ChatSandboxPage } from '@/pages/chat-sandbox-page'
import { ChatsPage } from '@/pages/chats-page'
import { ConversationsPage } from '@/pages/conversations-page'
import { ErrorPage } from '@/pages/error-page'
import { FaqPage } from '@/pages/faq-page'
import { HomePage } from '@/pages/home-page'
import { NotFoundPage } from '@/pages/not-found-page'
import { OrdersPage } from '@/pages/orders-page'
import { PaymentPage } from '@/pages/payment-page'
import { PaymentFailedPage, PaymentSuccessPage } from '@/pages/payment-status-page'
import { ProductOrdersPage } from '@/pages/product-orders-page'
import { ProductPage } from '@/pages/product-page'
import { QuestionsPage } from '@/pages/questions-page'
import { ServiceOrdersPage } from '@/pages/service-orders-page'
import { ServicePage } from '@/pages/service-page'
import { WorkflowPage } from '@/pages/workflow-page'

// All client-side routes. Add new pages here as children of the root layout, and add a tab in
// `@/config/navigation` if they belong in the top nav (or a section's sub-tabs).
// Pages that need a logged-in user go inside the `<RequireAuth />` group: their tabs are hidden
// while logged out, and opening their URL shows the login guard instead.
export const routes: RouteObject[] = [
  {
    path: paths.home,
    element: <RootLayout />,
    errorElement: <ErrorPage />,
    children: [
      { index: true, element: <HomePage /> },
      // Old URLs, from before the sections had sub-tabs.
      ...legacyRedirects.map(({ from, to }) => ({ path: from, element: <RedirectKeepingSearch to={to} /> })),
      // Public payment result pages (the customer is redirected here by Xendit).
      { path: paths.paymentSuccess, element: <PaymentSuccessPage /> },
      { path: paths.paymentFailed, element: <PaymentFailedPage /> },
      // Login required: shows a "you need to be logged in" message instead when logged out.
      {
        element: <RequireAuth />,
        children: [
          { path: paths.workflow, element: <WorkflowPage /> },
          {
            path: paths.catalog,
            element: <CatalogPage />,
            children: [
              { index: true, element: <SectionIndexRedirect to={paths.catalogProducts} /> },
              { path: paths.catalogProducts, element: <ProductPage /> },
              { path: paths.catalogServices, element: <ServicePage /> },
              { path: paths.catalogFaqs, element: <FaqPage /> },
            ],
          },
          {
            path: paths.orders,
            element: <OrdersPage />,
            children: [
              {
                index: true,
                element: <SectionIndexRedirect to={paths.productOrders} legacyTabs={{ services: paths.serviceOrders }} />,
              },
              { path: paths.productOrders, element: <ProductOrdersPage /> },
              { path: paths.serviceOrders, element: <ServiceOrdersPage /> },
              { path: paths.payment, element: <PaymentPage /> },
            ],
          },
          {
            path: paths.chats,
            element: <ChatsPage />,
            children: [
              {
                index: true,
                element: <SectionIndexRedirect to={paths.conversations} legacyTabs={{ questions: paths.questions }} />,
              },
              { path: paths.conversations, element: <ConversationsPage /> },
              { path: paths.questions, element: <QuestionsPage /> },
              { path: paths.chatSandbox, element: <ChatSandboxPage /> },
            ],
          },
        ],
      },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
]
