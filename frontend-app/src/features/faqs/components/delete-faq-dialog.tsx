import { ConfirmDialog } from '@/components/common/confirm-dialog'

import { useDeleteFaq } from '../hooks/use-faqs'
import type { Faq } from '../types'

interface DeleteFaqDialogProps {
  faq: Faq | null
  onOpenChange: (open: boolean) => void
  onError: (message: string) => void
}

export function DeleteFaqDialog({ faq, onOpenChange, onError }: DeleteFaqDialogProps) {
  const deleteFaq = useDeleteFaq()

  const handleConfirm = () => {
    if (!faq) return
    deleteFaq.mutate(faq.id, {
      onSuccess: () => onOpenChange(false),
      onError: (error) => {
        onOpenChange(false)
        onError(`Couldn't delete the FAQ: ${error.message}`)
      },
    })
  }

  return (
    <ConfirmDialog
      open={faq !== null}
      onOpenChange={onOpenChange}
      title="Delete FAQ?"
      description={<>“{faq?.question}” and its answer will be permanently deleted. This can't be undone.</>}
      confirmLabel="Delete"
      pendingLabel="Deleting…"
      destructive
      isPending={deleteFaq.isPending}
      onConfirm={handleConfirm}
    />
  )
}
