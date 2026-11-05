import { Check, Crown, Sparkles } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { useCurrentUser } from "@/features/auth";
import { cn } from "@/lib/utils";

import { type Plan, planFor, planRank, PLANS } from "../plans";
import { PlanCard, PricingNote } from "./plan-card";

const PLANS_SECTION_ID = "plans";
const TOP_PLAN = PLANS[PLANS.length - 1];

/** The logged-in account's plan (`subscription_tier` from GET /api/auth/me/); Free while it loads. */
function useCurrentPlan() {
  const { data: user } = useCurrentUser();
  return planFor(user?.subscription_tier);
}

/** The account's plan, for the welcome banner, with a link down to the plans. */
export function CurrentPlanBadge() {
  const plan = useCurrentPlan();
  const isTop = plan.id === TOP_PLAN.id;
  return (
    <div className="bg-background/80 flex items-center gap-3 rounded-2xl border px-4 py-3 shadow-sm backdrop-blur">
      <div
        className={cn(
          "flex size-9 items-center justify-center rounded-full",
          isTop
            ? "bg-amber-100 text-amber-600 dark:bg-amber-900/40 dark:text-amber-300"
            : "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/50 dark:text-emerald-300",
        )}
      >
        {isTop ? <Crown className="size-4" /> : <Sparkles className="size-4" />}
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
        {isTop ? (
          "View plans"
        ) : (
          <>
            <Crown className="text-amber-500" /> Upgrade
          </>
        )}
      </Button>
    </div>
  );
}

/** Every plan side by side, the account's own marked; paid plans aren't on sale yet. */
export function PlansSection() {
  const current = useCurrentPlan();
  const [interestedIn, setInterestedIn] = useState<Plan["id"] | null>(null);

  return (
    <section id={PLANS_SECTION_ID} className="flex scroll-mt-20 flex-col gap-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold tracking-tight">Plans</h2>
          <p className="text-muted-foreground text-sm">
            You're on the {current.name} plan.{" "}
            {current.id === TOP_PLAN.id
              ? "Every feature is included. Thanks for being with us!"
              : "Upgrade when your assistant is ready for more customers."}
          </p>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {PLANS.map((plan) => {
          const isCurrent = plan.id === current.id;
          const isIncluded = planRank(plan.id) < planRank(current.id);
          return (
            <PlanCard
              key={plan.id}
              plan={plan}
              highlight={isCurrent ? "current" : undefined}
              muted={isIncluded}
            >
              {isCurrent || isIncluded ? (
                <Button
                  variant="outline"
                  disabled
                  className={cn(
                    isCurrent &&
                      "border-amber-500 text-amber-700 opacity-100 disabled:opacity-100 dark:text-amber-400",
                  )}
                >
                  {isCurrent ? (
                    <>
                      <Check /> You're on this plan
                    </>
                  ) : (
                    `Included in ${current.name}`
                  )}
                </Button>
              ) : (
                <Button
                  variant="outline"
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
            </PlanCard>
          );
        })}
      </div>
      <PricingNote />
    </section>
  );
}
