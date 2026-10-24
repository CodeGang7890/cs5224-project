import { ConfirmDialog } from "@/components/common/confirm-dialog";

import { useDeleteProvider, useDeleteService } from "../hooks/use-services";
import type { Service, ServiceProvider } from "../types";

interface DeleteDialogProps<T> {
  item: T | null;
  onOpenChange: (open: boolean) => void;
  onError: (message: string) => void;
}

export function DeleteServiceDialog({
  item,
  onOpenChange,
  onError,
}: DeleteDialogProps<Service>) {
  const remove = useDeleteService();
  return (
    <ConfirmDialog
      open={item !== null}
      onOpenChange={onOpenChange}
      title="Delete service?"
      description={
        <>
          “{item?.name}” will be permanently deleted. Its bookings are kept (in
          the Orders tab). To stop new bookings without deleting it, edit it and
          turn off <strong>Active</strong>.
        </>
      }
      confirmLabel="Delete"
      pendingLabel="Deleting…"
      destructive
      isPending={remove.isPending}
      onConfirm={() =>
        item &&
        remove.mutate(item.id, {
          onSuccess: () => onOpenChange(false),
          onError: (error) => {
            onOpenChange(false);
            onError(`Couldn't delete “${item.name}”: ${error.message}`);
          },
        })
      }
    />
  );
}

export function DeleteProviderDialog({
  item,
  onOpenChange,
  onError,
}: DeleteDialogProps<ServiceProvider>) {
  const remove = useDeleteProvider();
  return (
    <ConfirmDialog
      open={item !== null}
      onOpenChange={onOpenChange}
      title="Delete service provider?"
      description={
        <>
          “{item?.name}” and their whole schedule will be permanently deleted,
          and removed from their services. Their bookings are kept (in the
          Orders tab). To stop new bookings without deleting them, edit them and
          turn off <strong>Active</strong>.
        </>
      }
      confirmLabel="Delete"
      pendingLabel="Deleting…"
      destructive
      isPending={remove.isPending}
      onConfirm={() =>
        item &&
        remove.mutate(item.id, {
          onSuccess: () => onOpenChange(false),
          onError: (error) => {
            onOpenChange(false);
            onError(`Couldn't delete “${item.name}”: ${error.message}`);
          },
        })
      }
    />
  );
}
