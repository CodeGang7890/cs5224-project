import { useEffect, useState } from 'react'
import { Pencil, Plus, Trash2 } from 'lucide-react'

import { PaginationControls } from '@/components/common/pagination-controls'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { usePageParam } from '@/hooks/use-page-param'

import { PRODUCTS_PAGE_SIZE, useProducts } from '../hooks/use-products'
import type { Product } from '../types'
import { DeleteProductDialog } from './delete-product-dialog'
import { ProductFormDialog } from './product-form-dialog'

const priceFormat = new Intl.NumberFormat(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
const quantityFormat = new Intl.NumberFormat()

type FormState = { open: false } | { open: true; product?: Product }

/** Product list with add / edit / delete for the logged-in user's business. */
export function ProductManager() {
  const [page, setPage] = usePageParam()
  const { data, isPending, isError, error, refetch, isPlaceholderData } = useProducts(page)
  const [form, setForm] = useState<FormState>({ open: false })
  const [deleting, setDeleting] = useState<Product | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)

  // Page out of range (e.g. deleted the last item on the last page): step back a page.
  useEffect(() => {
    if (isError && error.status === 404 && page > 1) setPage(page - 1)
  }, [isError, error, page, setPage])

  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-muted-foreground text-sm">
          {data ? `${data.count} product${data.count === 1 ? '' : 's'}` : ' '}
        </p>
        <Button onClick={() => setForm({ open: true })}>
          <Plus /> Add product
        </Button>
      </div>

      {actionError && (
        <p role="alert" className="text-destructive text-sm">
          {actionError}
        </p>
      )}

      {isPending ? (
        <div className="grid gap-2">
          {Array.from({ length: 5 }, (_, i) => (
            <Skeleton key={i} className="h-12 w-full" />
          ))}
        </div>
      ) : isError && !data ? (
        <div className="flex flex-col items-start gap-3 rounded-lg border border-destructive/50 p-4">
          <p className="text-destructive text-sm">Couldn't load products: {error.message}</p>
          <Button variant="outline" size="sm" onClick={() => refetch()}>
            Try again
          </Button>
        </div>
      ) : data.results.length === 0 ? (
        <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed p-10 text-center">
          <p className="font-medium">No products yet</p>
          <p className="text-muted-foreground text-sm">Add your first product to get started.</p>
          <Button variant="outline" onClick={() => setForm({ open: true })}>
            <Plus /> Add product
          </Button>
        </div>
      ) : (
        <div className={isPlaceholderData ? 'opacity-60 transition-opacity' : undefined}>
          <div className="rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="min-w-48">Name</TableHead>
                  <TableHead className="text-right">Price</TableHead>
                  <TableHead className="text-right">Available</TableHead>
                  <TableHead className="text-right">On hold</TableHead>
                  <TableHead className="text-right">Sold</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="w-24 text-right">
                    <span className="sr-only">Actions</span>
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.results.map((product) => (
                  <TableRow key={product.id}>
                    <TableCell className="max-w-80 whitespace-normal">
                      <div className="font-medium">{product.name}</div>
                      {product.description && (
                        <div className="text-muted-foreground line-clamp-1 text-xs">{product.description}</div>
                      )}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{priceFormat.format(Number(product.price))}</TableCell>
                    <TableCell className="text-right tabular-nums">{quantityFormat.format(product.quantity_available)}</TableCell>
                    <TableCell className="text-right tabular-nums">{quantityFormat.format(product.quantity_on_hold)}</TableCell>
                    <TableCell className="text-right tabular-nums">{quantityFormat.format(product.quantity_sold)}</TableCell>
                    <TableCell>
                      <Badge variant={product.is_active ? 'secondary' : 'outline'}>
                        {product.is_active ? 'Active' : 'Inactive'}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right">
                      <Button
                        variant="ghost"
                        size="icon"
                        aria-label={`Edit ${product.name}`}
                        onClick={() => setForm({ open: true, product })}
                      >
                        <Pencil />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        aria-label={`Delete ${product.name}`}
                        onClick={() => {
                          setActionError(null)
                          setDeleting(product)
                        }}
                      >
                        <Trash2 className="text-destructive" />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          <div className="mt-4">
            <PaginationControls
              page={page}
              pageSize={PRODUCTS_PAGE_SIZE}
              count={data.count}
              onPageChange={setPage}
              disabled={isPlaceholderData}
            />
          </div>
        </div>
      )}

      <ProductFormDialog
        open={form.open}
        onOpenChange={(open) => !open && setForm({ open: false })}
        product={form.open ? form.product : undefined}
      />
      <DeleteProductDialog
        product={deleting}
        onOpenChange={(open) => !open && setDeleting(null)}
        onError={setActionError}
      />
    </div>
  )
}
