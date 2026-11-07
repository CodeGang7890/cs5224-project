import { ConfirmDialog } from "@/components/common/confirm-dialog";

import { useDeleteProduct } from "../hooks/use-products";
import type { Product } from "../types";

interface DeleteProductDialogProps {
  product: Product | null;
  onOpenChange: (open: boolean) => void;
  onError: (message: string) => void;
}

export function DeleteProductDialog({
  product,
  onOpenChange,
  onError,
}: DeleteProductDialogProps) {
  const deleteProduct = useDeleteProduct();

  const handleConfirm = () => {
    if (!product) return;
    deleteProduct.mutate(product.id, {
      onSuccess: () => onOpenChange(false),
      onError: (error) => {
        onOpenChange(false);
        onError(`Couldn't delete “${product.name}”: ${error.message}`);
      },
    });
  };

  return (
    <ConfirmDialog
      open={product !== null}
      onOpenChange={onOpenChange}
      title="Delete product?"
      description={
        <>
          “{product?.name}” will be permanently deleted. This can't be undone.
          To hide a product without deleting it, edit it and turn off{" "}
          <strong>Active</strong>.
        </>
      }
      confirmLabel="Delete"
      pendingLabel="Deleting…"
      destructive
      isPending={deleteProduct.isPending}
      onConfirm={handleConfirm}
    />
  );
}
