import { ConfirmDialog } from '@/components/common/confirm-dialog'

import { useDeleteAvailability, useDeleteService } from '../hooks/use-services'
import type { Service, WeeklyAvailability } from '../types'

interface DeleteDialogProps<T> {
  item: T | null
  onOpenChange: (open: boolean) => void
  onError: (message: string) => void
}

export function DeleteServiceDialog({ item, onOpenChange, onError }: DeleteDialogProps<Service>) {
  const remove = useDeleteService()
  return (
    <ConfirmDialog
      open={item !== null}
      onOpenChange={onOpenChange}
      title="Delete service?"
      description={
        <>
          “{item?.name}” will be permanently deleted. Its bookings are kept (in the Orders tab). To stop new bookings
          without deleting it, edit it and turn off <strong>Active</strong>.
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
            onOpenChange(false)
            onError(`Couldn't delete “${item.name}”: ${error.message}`)
          },
        })
      }
    />
  )
}

export function DeleteAvailabilityDialog({ item, onOpenChange, onError }: DeleteDialogProps<WeeklyAvailability>) {
  const remove = useDeleteAvailability()
  return (
    <ConfirmDialog
      open={item !== null}
      onOpenChange={onOpenChange}
      title="Delete weekly availability?"
      description={
        <>
          “{item?.name}” will be permanently deleted and removed from its services. Its bookings are kept (in the
          Orders tab), but no longer block anyone's calendar.
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
            onOpenChange(false)
            onError(`Couldn't delete “${item.name}”: ${error.message}`)
          },
        })
      }
    />
  )
}
