import { Check, Crown, Sparkles } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

import {
  CURRENT_PLAN_ID,
  currentPlan,
  formatPrice,
  type Plan,
  PLANS,
} from "../plans";

const PLANS_SECTION_ID = "plans";

/** The account's plan, for the welcome banner, with a link down to the plans. */
export function CurrentPlanBadge() {
  const plan = currentPlan();
  return (
    <div className="bg-background/80 flex items-center gap-3 rounded-2xl border px-4 py-3 shadow-sm backdrop-blur">
      <div className="flex size-9 items-center justify-center rounded-full bg-emerald-100 text-emerald-700 dark:bg-emerald-900/50 dark:text-emerald-300">
        <Sparkles className="size-4" />
      </div>
      <div className="leading-tight">
        <p className="text-muted-foreground text-xs">Your plan</p>
        <p className="font-semibold">{plan.name}</p>
      </div>
      <Button
        size="sm"
        variant="outline"
        className="ml-2"
        onClick={() =>
          document
            .getElementById(PLANS_SECTION_ID)
            ?.scrollIntoView({ behavior: "smooth" })
        }
      >
        <Crown className="text-amber-500" /> Upgrade
      </Button>
    </div>
  );
}

/** Every plan side by side, the account's own marked; paid plans aren't on sale yet. */
export function PlansSection() {
  const [interestedIn, setInterestedIn] = useState<Plan["id"] | null>(null);

  return (
    <section id={PLANS_SECTION_ID} className="flex scroll-mt-20 flex-col gap-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold tracking-tight">Plans</h2>
          <p className="text-muted-foreground text-sm">
            You're on the {currentPlan().name} plan. Upgrade when your assistant
            is ready for more customers.
          </p>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {PLANS.map((plan) => {
          const isCurrent = plan.id === CURRENT_PLAN_ID;
          return (
            <div
              key={plan.id}
              className={cn(
                "bg-card relative flex flex-col gap-4 rounded-2xl border p-6 transition-all duration-300 hover:-translate-y-1 hover:shadow-lg",
                plan.recommended &&
                  "border-emerald-500 shadow-md ring-1 shadow-emerald-600/10 ring-emerald-500",
                isCurrent && "bg-muted/40",
              )}
            >
              {plan.recommended && (
                <Badge className="absolute -top-2.5 left-6 bg-emerald-600 text-white">
                  Recommended
                </Badge>
              )}
              <div>
                <p className="flex items-center gap-2 font-semibold">
                  {plan.name}
                  {isCurrent && <Badge variant="outline">Current plan</Badge>}
                </p>
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
              {isCurrent ? (
                <Button variant="outline" disabled>
                  Your current plan
                </Button>
              ) : (
                <Button
                  variant={plan.recommended ? "default" : "outline"}
                  onClick={() => setInterestedIn(plan.id)}
                >
                  Upgrade to {plan.name}
                </Button>
              )}
              {interestedIn === plan.id && (
                <p
                  role="status"
                  className="animate-in fade-in text-muted-foreground -mt-2 text-center text-xs"
                >
                  Paid plans are coming soon. Thanks for your interest!
                </p>
              )}
            </div>
          );
        })}
      </div>
      <p className="text-muted-foreground text-xs">
        WhatsApp messaging fees and AI usage are billed separately, at cost with
        no markup, and you can set a monthly spending cap.
      </p>
    </section>
  );
}
