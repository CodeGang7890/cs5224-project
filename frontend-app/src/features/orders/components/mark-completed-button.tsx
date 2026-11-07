import { useState } from "react";
import { CircleCheck } from "lucide-react";

import { ConfirmDialog } from "@/components/common/confirm-dialog";
import { Button } from "@/components/ui/button";
import { getFormErrors } from "@/lib/form-errors";

import { useCompleteOrder } from "../hooks/use-orders";
import { useCompleteSchedule } from "../hooks/use-schedules";

interface MarkCompletedButtonProps {
  kind: "order" | "booking";
  id: number;
}

/**
 * Payment received → completed, after a confirmation. Only shown for paid orders / bookings
 * (pending payment → payment received is set by the payment service, not here).
 */
export function MarkCompletedButton({ kind, id }: MarkCompletedButtonProps) {
  const completeOrder = useCompleteOrder();
  const completeSchedule = useCompleteSchedule();
  const mutation = kind === "order" ? completeOrder : completeSchedule;
  const [open, setOpen] = useState(false);
  const errors = mutation.error ? getFormErrors(mutation.error) : null;
  const error =
    errors &&
    (errors.fields.order_status ?? errors.form ?? mutation.error?.message);

  return (
    <>
      <Button
        onClick={() => {
          mutation.reset();
          setOpen(true);
        }}
      >
        <CircleCheck /> Mark as completed
      </Button>
      <ConfirmDialog
        open={open}
        onOpenChange={setOpen}
        title={`Mark ${kind} #${id} as completed?`}
        description={
          <span className="grid gap-2">
            <span>
              {kind === "order"
                ? "Its status changes from Payment received to Completed, and its products count as sold."
                : "Its status changes from Payment received to Completed. Its time stays booked."}{" "}
              This can't be undone here.
            </span>
            {error && (
              <span role="alert" className="text-destructive">
                Couldn't update it: {error}
              </span>
            )}
          </span>
        }
        confirmLabel="Mark as completed"
        pendingLabel="Saving…"
        isPending={mutation.isPending}
        onConfirm={() =>
          mutation.mutate(id, { onSuccess: () => setOpen(false) })
        }
      />
    </>
  );
}
