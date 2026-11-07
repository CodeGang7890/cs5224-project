import type { LucideIcon } from "lucide-react";
import {
  ArrowRight,
  MessagesSquare,
  Package,
  Receipt,
  Sparkles,
  Workflow,
} from "lucide-react";
import { Link } from "react-router";

import { Card, CardContent } from "@/components/ui/card";
import { paths } from "@/config/navigation";
import { useCurrentUser } from "@/features/auth";
import { CreateBusinessCard, useNeedsBusiness } from "@/features/business";
import { WhatsAppSettingsCard } from "@/features/whatsapp";

import { CurrentPlanBadge, PlansSection } from "./plans-section";
import { SetupChecklist } from "./setup-checklist";

interface QuickLink {
  icon: LucideIcon;
  title: string;
  description: string;
  to: string;
}

const QUICK_LINKS: QuickLink[] = [
  {
    icon: Workflow,
    title: "Workflow",
    description: "The welcome message, reply style and details to collect.",
    to: paths.workflow,
  },
  {
    icon: Package,
    title: "Catalog",
    description: "Products, services and FAQs your assistant knows about.",
    to: paths.catalog,
  },
  {
    icon: Receipt,
    title: "Orders",
    description: "Orders, bookings and payments from your chats.",
    to: paths.orders,
  },
  {
    icon: MessagesSquare,
    title: "Chats",
    description: "Read conversations and answer the questions it couldn't.",
    to: paths.chats,
  },
];

/** The Home page while logged in: a welcome with the plan, setting up (business, catalog, WhatsApp), shortcuts and the plans. */
export function BusinessHome() {
  const { data: user } = useCurrentUser();
  // A new account sets up its business first; everything else comes after that.
  const needsBusiness = useNeedsBusiness();
  const name = user?.first_name || user?.username;

  return (
    <div className="flex flex-col gap-8">
      <section className="flex flex-wrap items-center justify-between gap-6 rounded-3xl border bg-gradient-to-br from-emerald-50 via-background to-sky-50 px-6 py-8 sm:px-10 dark:from-emerald-950/40 dark:to-sky-950/30">
        <div>
          <p className="flex items-center gap-1.5 text-sm font-medium text-emerald-700 dark:text-emerald-400">
            <Sparkles className="size-4" />
            {user?.business_name ?? "Your AI sales assistant"}
          </p>
          <h1 className="mt-2 text-3xl font-bold tracking-tight">
            {name ? `Welcome back, ${name}!` : "Welcome back!"}
          </h1>
          <p className="text-muted-foreground mt-2 max-w-2xl">
            {needsBusiness
              ? "Let's set up your business. It takes less than a minute, and then your assistant can start selling for you."
              : "Your assistant answers customers on WhatsApp around the clock, taking orders, booking appointments and sending payment links."}
          </p>
        </div>
        <CurrentPlanBadge />
      </section>

      {needsBusiness ? (
        <CreateBusinessCard />
      ) : (
        <>
          {/* Side by side on wide screens; the WhatsApp card's own width cap is lifted to fill its column. */}
          <div className="grid items-stretch gap-6 lg:grid-cols-2 *:max-w-none">
            {user?.business != null && <SetupChecklist />}
            <WhatsAppSettingsCard />
          </div>
          {user?.business != null && (
            <section className="flex flex-col gap-4">
              <h2 className="text-xl font-semibold tracking-tight">
                Jump back in
              </h2>
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                {QUICK_LINKS.map(({ icon: Icon, title, description, to }) => (
                  <Link key={to} to={to} className="group">
                    <Card className="h-full gap-2 transition-shadow group-hover:shadow-md">
                      <CardContent className="flex flex-col gap-2">
                        <Icon className="size-5 text-emerald-600" />
                        <p className="flex items-center gap-1 font-semibold">
                          {title}
                          <ArrowRight className="size-4 transition-transform group-hover:translate-x-0.5" />
                        </p>
                        <p className="text-muted-foreground text-sm">
                          {description}
                        </p>
                      </CardContent>
                    </Card>
                  </Link>
                ))}
              </div>
            </section>
          )}
          <PlansSection />
        </>
      )}
    </div>
  );
}
