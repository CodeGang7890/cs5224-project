import { useState, type FormEvent } from "react";

import { FormField } from "@/components/common/form-field";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { getFormErrors } from "@/lib/form-errors";

import { useMyBusiness, useSavePaymentExpiry } from "../hooks/use-my-business";
import type { Business } from "../types";

export function PaymentExpiryCard() {
  const business = useMyBusiness();
  if (business.isPending) return <p role="status">Loading payment settings…</p>;
  if (business.isError)
    return (
      <div role="alert" className="flex items-center gap-3">
        <p>Could not load payment settings.</p>
        <Button variant="outline" onClick={() => void business.refetch()}>
          Retry
        </Button>
      </div>
    );
  if (!business.data) return null;
  return <PaymentExpiryForm key={business.data.id} business={business.data} />;
}

function PaymentExpiryForm({ business }: { business: Business }) {
  const save = useSavePaymentExpiry();
  const [draft, setDraft] = useState<string | null>(null);
  const [validation, setValidation] = useState<string>();
  const value = draft ?? String(business.payment_expiry_minutes);
  const minutes = Number(value);
  const server = save.error ? getFormErrors(save.error) : undefined;

  function submit(event: FormEvent) {
    event.preventDefault();
    if (
      !value.trim() ||
      !Number.isInteger(minutes) ||
      minutes < 1 ||
      minutes > 2147483647
    ) {
      setValidation("Enter a positive whole number of minutes.");
      return;
    }
    setValidation(undefined);
    save.mutate(minutes, { onSuccess: () => setDraft(null) });
  }

  return (
    <Card className="mb-6">
      <CardHeader>
        <CardTitle>Payment link expiry</CardTitle>
        <CardDescription>
          Choose how long customers have to pay for new orders and bookings. The
          default is 180 minutes (3 hours). Existing payment links keep their
          original expiry.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form
          onSubmit={submit}
          className="flex max-w-xl flex-col items-start gap-4"
        >
          <FormField
            id="payment-expiry-minutes"
            label="Expires after (minutes)"
            error={validation ?? server?.fields.payment_expiry_minutes}
            hint="Counted from when each payment link is issued."
            required
          >
            <Input
              id="payment-expiry-minutes"
              type="number"
              min={1}
              max={2147483647}
              step={1}
              value={value}
              disabled={save.isPending}
              required
              aria-describedby="payment-expiry-minutes-message"
              onChange={(event) => {
                setDraft(event.target.value);
                setValidation(undefined);
                save.reset();
              }}
            />
          </FormField>
          {save.isError && (
            <p role="alert" className="text-destructive text-sm">
              {server?.form ??
                "Could not save payment settings. Please try again."}
            </p>
          )}
          <div className="flex items-center gap-3">
            <Button
              type="submit"
              disabled={
                save.isPending || minutes === business.payment_expiry_minutes
              }
            >
              {save.isPending ? "Saving…" : "Save payment settings"}
            </Button>
            {save.isSuccess && (
              <p role="status" className="text-muted-foreground text-sm">
                Payment settings saved.
              </p>
            )}
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
