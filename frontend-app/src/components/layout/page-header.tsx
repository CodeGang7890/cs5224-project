import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

import { type Accent, ACCENTS } from "./accents";

/** A page's heading: a soft banner in the section's accent, its icon, title, description and actions. */
export function PageHeader({
  icon: Icon,
  accent,
  title,
  description,
  actions,
}: {
  icon: LucideIcon;
  accent: Accent;
  title: string;
  description: ReactNode;
  actions?: ReactNode;
}) {
  const colors = ACCENTS[accent];
  return (
    <div
      className={cn(
        "via-background to-background flex flex-wrap items-center justify-between gap-4 rounded-2xl border bg-gradient-to-br px-5 py-4",
        colors.banner,
      )}
    >
      <div className="flex min-w-0 items-center gap-4">
        <div
          className={cn(
            "flex size-11 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br text-white shadow-md",
            colors.tile,
          )}
        >
          <Icon className="size-5" />
        </div>
        <div className="grid min-w-0 gap-0.5">
          <h1 className="text-2xl font-bold tracking-tight">{title}</h1>
          <p className="text-muted-foreground text-sm">{description}</p>
        </div>
      </div>
      {actions}
    </div>
  );
}
