import { ArrowRight } from "lucide-react";

import { Skeleton } from "@/components/ui/skeleton";

import { useSubscriptionTiers } from "../hooks/use-subscription-tiers";
import { type Plan, PLANS } from "../plans";
import { AuthButton } from "./auth-button";
import { PlanCard, PricingNote } from "./plan-card";
import { Reveal } from "./reveal";

/**
 * The landing page's pricing: the plans configuration-service offers (GET /api/auth/subscription-tiers/,
 * their order and names) with this app's prices and features. Every button signs up (on Free).
 */
export function PricingSection() {
  const { data: tiers, isPending, isError } = useSubscriptionTiers();

  // The backend decides which plans exist; if it can't be reached, show the ones known here.
  const plans: Plan[] = isError
    ? PLANS
    : (tiers ?? []).flatMap((tier) => {
        const plan = PLANS.find((known) => known.id === tier.id);
        return plan ? [{ ...plan, name: tier.name }] : [];
      });

  return (
    <section className="flex flex-col gap-10">
      <Reveal className="mx-auto max-w-2xl text-center">
        <p className="text-sm font-semibold tracking-wide text-emerald-600 uppercase">
          Pricing
        </p>
        <h2 className="mt-2 text-3xl font-bold tracking-tight">
          Start free, upgrade as you grow
        </h2>
        <p className="text-muted-foreground mt-3 text-lg">
          Every account starts on Free. Pick a paid plan when your assistant is
          ready for more customers.
        </p>
      </Reveal>
      <div className="grid gap-4 pt-2 md:grid-cols-2 xl:grid-cols-4">
        {isPending && !isError
          ? Array.from({ length: 4 }, (_, index) => (
              <Skeleton key={index} className="h-96 rounded-2xl" />
            ))
          : plans.map((plan, index) => (
              <Reveal key={plan.id} delay={(index % 4) * 100}>
                <PlanCard
                  plan={plan}
                  highlight={plan.recommended ? "recommended" : undefined}
                >
                  <AuthButton
                    mode="signup"
                    variant={plan.recommended ? "default" : "outline"}
                    className="group"
                  >
                    {plan.price === 0
                      ? "Start for free"
                      : `Get started with ${plan.name}`}
                    <ArrowRight className="transition-transform group-hover:translate-x-1" />
                  </AuthButton>
                </PlanCard>
              </Reveal>
            ))}
      </div>
      <PricingNote />
    </section>
  );
}
