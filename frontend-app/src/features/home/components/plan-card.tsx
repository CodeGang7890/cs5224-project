import { Check, Crown } from "lucide-react";
import type { ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

import { formatPrice, type Plan } from "../plans";

/**
 * One plan: name, price, usage and features, with `children` (its button) at the bottom. `highlight`:
 * `current` (the account's own plan: the only framed card), `recommended` (for visitors with no plan yet)
 * or none; `muted` fades a plan the account's one already includes.
 */
export function PlanCard({
  plan,
  highlight,
  muted = false,
  children,
}: {
  plan: Plan;
  highlight?: "current" | "recommended";
  muted?: boolean;
  children: ReactNode;
}) {
  return (
    <div
      className={cn(
        "bg-card relative flex h-full flex-col gap-4 rounded-2xl border p-6 transition-all duration-300 hover:-translate-y-1 hover:shadow-lg",
        highlight === "recommended" &&
          "border-emerald-500 shadow-md ring-1 shadow-emerald-600/10 ring-emerald-500",
        highlight === "current" &&
          "border-amber-400 bg-amber-50/70 shadow-lg ring-2 shadow-amber-500/20 ring-amber-400 dark:border-amber-500 dark:bg-amber-950/25 dark:ring-amber-500",
        muted && "opacity-60 hover:opacity-100",
      )}
    >
      {highlight === "recommended" && (
        <Badge className="absolute -top-2.5 left-6 bg-emerald-600 text-white">
          Recommended
        </Badge>
      )}
      {highlight === "current" && (
        <Badge className="absolute -top-3 left-6 gap-1 bg-amber-500 px-2.5 py-1 text-white shadow">
          <Crown /> Your plan
        </Badge>
      )}
      <div>
        <p className="font-semibold">{plan.name}</p>
        <p className="text-muted-foreground text-sm">{plan.tagline}</p>
      </div>
      <p>
        <span className="text-3xl font-bold tracking-tight">
          {formatPrice(plan.price)}
        </span>
        {plan.price > 0 && (
          <span className="text-muted-foreground text-sm">/month</span>
        )}
      </p>
      <p className="text-sm font-medium text-emerald-700 dark:text-emerald-400">
        {plan.usage}
      </p>
      <ul className="flex flex-1 flex-col gap-2 text-sm">
        {plan.features.map((feature) => (
          <li key={feature} className="flex items-start gap-2">
            {feature.endsWith(":") ? (
              <span className="text-muted-foreground font-medium">
                {feature}
              </span>
            ) : (
              <>
                <Check className="mt-0.5 size-4 shrink-0 text-emerald-600" />
                {feature}
              </>
            )}
          </li>
        ))}
      </ul>
      {children}
    </div>
  );
}

/** The pricing fine print shown under the plans. */
export function PricingNote() {
  return (
    <p className="text-muted-foreground text-xs">
      Prices exclude VAT. An interaction is one customer's conversation: all
      their messages within 24 hours. WhatsApp messaging fees are billed
      separately, at cost with no markup.
    </p>
  );
}
