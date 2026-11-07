import { type QueryKey, useQueryClient } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

// Keeps the spin visible briefly, so a fast refresh still looks like it did something.
const MIN_SPIN_MS = 600;

/**
 * A Refresh button for a section's data: re-fetches the active queries under `queryKeys` at once.
 * The Catalog and Orders lists don't poll (the user asked, for demos: a change shows only after a
 * Refresh, so it's clear when the page was refreshed); this is how they get other services' changes.
 */
export function RefreshButton({ queryKeys }: { queryKeys: QueryKey[] }) {
  const queryClient = useQueryClient();
  const [refreshing, setRefreshing] = useState(false);

  const refresh = async () => {
    setRefreshing(true);
    const started = Date.now();
    await Promise.allSettled(
      queryKeys.map((queryKey) =>
        queryClient.refetchQueries({ queryKey, type: "active" }),
      ),
    );
    const left = MIN_SPIN_MS - (Date.now() - started);
    if (left > 0) await new Promise((resolve) => setTimeout(resolve, left));
    setRefreshing(false);
  };

  return (
    <Button
      variant="outline"
      size="sm"
      onClick={refresh}
      disabled={refreshing}
      className="shrink-0"
    >
      <RefreshCw className={cn(refreshing && "animate-spin")} />
      {refreshing ? "Refreshing…" : "Refresh"}
    </Button>
  );
}
