import { ExternalLink } from "lucide-react";

import { Button } from "@/components/ui/button";

import { PaymentReference } from "./payment-reference";

export interface PaymentDetailsProps {
  reference: string;
  xenditPaymentId: string | null;
  paymentLink: string | null;
}

/** The payment an order / booking is made under, and the Xendit link (when one was created). */
export function PaymentDetails({
  reference,
  xenditPaymentId,
  paymentLink,
}: PaymentDetailsProps) {
  return (
    <div className="grid gap-3">
      <PaymentReference reference={reference} />

      <div className="grid min-w-0 gap-0.5">
        <span className="text-muted-foreground text-xs">Xendit payment ID</span>
        {xenditPaymentId ? (
          <code className="truncate font-mono text-sm" title={xenditPaymentId}>
            {xenditPaymentId}
          </code>
        ) : (
          <span className="text-muted-foreground text-sm">Not created yet</span>
        )}
      </div>

      <div className="grid min-w-0 gap-0.5">
        <span className="text-muted-foreground text-xs">Payment link</span>
        {paymentLink ? (
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="w-fit gap-1.5"
            asChild
          >
            <a href={paymentLink} target="_blank" rel="noreferrer">
              Open on Xendit <ExternalLink className="size-3.5" />
            </a>
          </Button>
        ) : (
          <span className="text-muted-foreground text-sm">Not created yet</span>
        )}
      </div>
    </div>
  );
}
