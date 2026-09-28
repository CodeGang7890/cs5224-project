import { createBrowserRouter } from 'react-router'

import { RootLayout } from '@/components/layout/root-layout'
import { ErrorPage } from '@/pages/error-page'
import { HomePage } from '@/pages/home-page'
import { NotFoundPage } from '@/pages/not-found-page'
import { PostDetailPage } from '@/pages/post-detail-page'
import { PostsPage } from '@/pages/posts-page'

// All client-side routes. Add new pages here as children of the root layout.
export const router = createBrowserRouter([
  {
    path: '/',
    element: <RootLayout />,
    errorElement: <ErrorPage />,
    children: [
      { index: true, element: <HomePage /> },
      { path: 'posts', element: <PostsPage /> },
      { path: 'posts/:postId', element: <PostDetailPage /> },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
])
