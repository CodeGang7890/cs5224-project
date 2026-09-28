import type { ReactNode } from 'react'
import { QueryClientProvider } from '@tanstack/react-query'
import { ReactQueryDevtools } from '@tanstack/react-query-devtools'

import { useApplyTheme } from '@/hooks/use-apply-theme'
import { queryClient } from '@/lib/query-client'

/** App-wide context providers. Wrap new global providers (auth, toasts, …) here. */
export function AppProviders({ children }: { children: ReactNode }) {
  useApplyTheme()

  return (
    <QueryClientProvider client={queryClient}>
      {children}
      {/* Devtools render only in development builds. */}
      <ReactQueryDevtools initialIsOpen={false} />
    </QueryClientProvider>
  )
}
