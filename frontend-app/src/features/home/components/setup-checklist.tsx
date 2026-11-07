import type { LucideIcon } from "lucide-react";
import {
  ArrowRight,
  Circle,
  CircleCheck,
  FlaskConical,
  Package,
  Store,
  Unplug,
} from "lucide-react";
import { Link } from "react-router";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { paths } from "@/config/navigation";
import { useHasActiveProducts } from "@/features/products";
import { useHasBookableServices } from "@/features/services";
import { useWhatsAppConfiguration } from "@/features/whatsapp";
import { cn } from "@/lib/utils";

interface Step {
  icon: LucideIcon;
  title: string;
  description: string;
  /** Undefined while loading (shown as not done yet). */
  done: boolean | undefined;
  action?: { label: string; to: string };
}

/**
 * The logged-in Home's "get your assistant selling" checklist: the business (always done here),
 * WhatsApp connected, something to sell, and a test in the Chat Sandbox.
 */
export function SetupChecklist() {
  const whatsApp = useWhatsAppConfiguration();
  const hasProducts = useHasActiveProducts();
  const hasServices = useHasBookableServices();

  const whatsAppHealth = whatsApp.data?.health;
  const whatsAppDone = whatsApp.isSuccess
    ? whatsAppHealth === "ok" || whatsAppHealth === "expiring_soon"
    : undefined;
  const catalogDone =
    hasProducts.data || hasServices.data
      ? true
      : hasProducts.isSuccess && hasServices.isSuccess
        ? false
        : undefined;

  const steps: Step[] = [
    {
      icon: Store,
      title: "Create your business",
      description:
        "Your assistant introduces itself with your business's name.",
      done: true,
    },
    {
      icon: Package,
      title: "Add what you sell",
      description:
        "Add active products or services (with a provider), so your assistant can sell them.",
      done: catalogDone,
      action: { label: "Open Catalog", to: paths.catalog },
    },
    {
      icon: Unplug,
      title: "Connect WhatsApp",
      description:
        "Link your WhatsApp Business number with Facebook (below), and customers' messages reach your assistant.",
      done: whatsAppDone,
    },
  ];
  const doneCount = steps.filter((step) => step.done).length;
  const allDone = doneCount === steps.length;

  return (
    <Card className="h-full">
      <CardHeader>
        <CardTitle>
          {allDone ? "Your assistant is live 🎉" : "Get your assistant selling"}
        </CardTitle>
        <CardDescription>
          {allDone
            ? "Everything is set up. Customers who message you on WhatsApp are answered right away."
            : `${doneCount} of ${steps.length} done. A few minutes more and your assistant starts answering customers.`}
        </CardDescription>
        <div
          className="bg-muted mt-2 h-2 overflow-hidden rounded-full"
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={steps.length}
          aria-valuenow={doneCount}
        >
          <div
            className="h-full rounded-full bg-emerald-600 transition-[width]"
            style={{ width: `${(doneCount / steps.length) * 100}%` }}
          />
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <ul className="flex flex-col gap-3">
          {steps.map((step) => (
            <ChecklistItem key={step.title} step={step} />
          ))}
        </ul>
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-dashed p-4">
          <div className="flex items-start gap-3">
            <FlaskConical className="mt-0.5 size-5 shrink-0 text-emerald-600" />
            <div>
              <p className="font-medium">Try it yourself</p>
              <p className="text-muted-foreground text-sm">
                Chat with your assistant as a pretend customer in the Chat
                Sandbox.
              </p>
            </div>
          </div>
          <Button asChild size="sm">
            <Link to={paths.chatSandbox}>
              Open Chat Sandbox <ArrowRight />
            </Link>
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function ChecklistItem({ step }: { step: Step }) {
  const { icon: Icon, title, description, done, action } = step;
  return (
    <li className="flex items-start gap-3">
      {done ? (
        <CircleCheck className="mt-0.5 size-5 shrink-0 text-emerald-600" />
      ) : (
        <Circle className="text-muted-foreground mt-0.5 size-5 shrink-0" />
      )}
      <div className="flex-1">
        <p
          className={cn(
            "flex items-center gap-2 font-medium",
            done && "text-muted-foreground line-through",
          )}
        >
          <Icon className="size-4" /> {title}
        </p>
        {!done && (
          <p className="text-muted-foreground text-sm">{description}</p>
        )}
      </div>
      {!done && action && (
        <Button asChild size="sm" variant="outline">
          <Link to={action.to}>{action.label}</Link>
        </Button>
      )}
    </li>
  );
}
