import { APP_NAME } from "@/config/app";
import { useHasActiveProducts } from "@/features/products";
import { useHasBookableServices } from "@/features/services";
import { WorkflowBuilder } from "@/features/workflow";

export function WorkflowPage() {
  // A route customers can't take (no active products / no bookable services) is greyed out.
  // Unknown while loading: nothing is greyed out until we know.
  const products = useHasActiveProducts();
  const services = useHasBookableServices();
  const unavailableRoutes = [
    ...(products.data === false ? (["orders"] as const) : []),
    ...(services.data === false ? (["bookings"] as const) : []),
  ];

  return (
    <section className="flex flex-col gap-6">
      <title>{`Workflow | ${APP_NAME}`}</title>
      <div className="grid gap-1">
        <h1 className="text-2xl font-bold tracking-tight">Workflow</h1>
        <p className="text-muted-foreground text-sm">
          How your chat assistant handles each customer message. Click a step to
          see what it does or to change its settings.
        </p>
      </div>
      <WorkflowBuilder unavailableRoutes={unavailableRoutes} />
    </section>
  );
}
