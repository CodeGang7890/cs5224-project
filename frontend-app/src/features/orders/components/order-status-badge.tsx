import { Badge } from "@/components/ui/badge";

import { ORDER_STATUS_META } from "../status";
import type { OrderStatus } from "../types";

export function OrderStatusBadge({ status }: { status: OrderStatus }) {
  const meta = ORDER_STATUS_META[status];
  return (
    <Badge variant="outline" className={meta.className}>
      {meta.label}
    </Badge>
  );
}

export function SandboxBadge() {
  return (
    <Badge
      variant="outline"
      className="border-amber-500/50 text-amber-700 dark:text-amber-400"
    >
      Sandbox
    </Badge>
  );
}
