import { CheckCircle2, CircleX, Home } from "lucide-react";

import { Button } from "@/components/ui/button";
import { APP_NAME } from "@/config/app";

function PaymentResultPage({
  succeeded,
  title,
  message,
}: {
  succeeded: boolean;
  title: string;
  message: string;
}) {
  const Icon = succeeded ? CheckCircle2 : CircleX;
  return (
    <div className="grid min-h-[50svh] place-items-center">
      <div className="flex max-w-md flex-col items-center gap-4 rounded-xl border p-8 text-center">
        <title>{`${title} | ${APP_NAME}`}</title>
        <Icon
          className={
            succeeded ? "size-12 text-emerald-500" : "size-12 text-red-500"
          }
        />
        <h1 className="text-xl font-semibold">{title}</h1>
        <p className="text-muted-foreground text-sm">{message}</p>
        <Button variant="outline" asChild>
          <a href="/">
            <Home /> Back to {APP_NAME}
          </a>
        </Button>
      </div>
    </div>
  );
}

/** Public result page the customer lands on after a successful Xendit payment. */
export function PaymentSuccessPage() {
  return (
    <PaymentResultPage
      succeeded
      title="Payment successful"
      message="Your payment went through. The business has been notified, and your order or booking is being updated."
    />
  );
}

/** Public result page the customer lands on after a failed or canceled Xendit payment. */
export function PaymentFailedPage() {
  return (
    <PaymentResultPage
      succeeded={false}
      title="Payment not completed"
      message="Your payment didn't go through. If you think this is a mistake, please contact the business."
    />
  );
}
