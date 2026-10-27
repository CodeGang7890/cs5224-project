import type { ReactNode } from "react";
import { QueryClientProvider } from "@tanstack/react-query";
import { ReactQueryDevtools } from "@tanstack/react-query-devtools";

import { useResetQueriesOnAuthChange } from "@/features/auth";
import { useApplyTheme } from "@/hooks/use-apply-theme";
import { queryClient } from "@/lib/query-client";

/** App-wide side effects that need the providers above them (e.g. the QueryClient). */
function GlobalEffects() {
  useResetQueriesOnAuthChange();
  return null;
}

/** App-wide context providers. Wrap new global providers (auth, toasts, …) here. */
export function AppProviders({ children }: { children: ReactNode }) {
  useApplyTheme();

  return (
    <QueryClientProvider client={queryClient}>
      <GlobalEffects />
      {children}
      {/* Devtools render only in development builds. */}
      <ReactQueryDevtools initialIsOpen={false} />
    </QueryClientProvider>
  );
}
