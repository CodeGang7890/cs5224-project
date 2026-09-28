import { useEffect, useState } from 'react'
import { Pencil, Plus, Trash2 } from 'lucide-react'

import { PaginationControls } from '@/components/common/pagination-controls'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { usePageParam } from '@/hooks/use-page-param'

import { FAQS_PAGE_SIZE, useFaqs } from '../hooks/use-faqs'
import type { Faq } from '../types'
import { DeleteFaqDialog } from './delete-faq-dialog'
import { FaqFormDialog } from './faq-form-dialog'

type FormState = { open: false } | { open: true; faq?: Faq }

/** FAQ list with add / edit / delete for the logged-in user's business. */
export function FaqManager() {
  const [page, setPage] = usePageParam()
  const { data, isPending, isError, error, refetch, isPlaceholderData } = useFaqs(page)
  const [form, setForm] = useState<FormState>({ open: false })
  const [deleting, setDeleting] = useState<Faq | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)

  // Page out of range (e.g. deleted the last item on the last page): step back a page.
  useEffect(() => {
    if (isError && error.status === 404 && page > 1) setPage(page - 1)
  }, [isError, error, page, setPage])

  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-muted-foreground text-sm">
          {data ? `${data.count} FAQ${data.count === 1 ? '' : 's'}` : ' '}
        </p>
        <Button onClick={() => setForm({ open: true })}>
          <Plus /> Add FAQ
        </Button>
      </div>

      {actionError && (
        <p role="alert" className="text-destructive text-sm">
          {actionError}
        </p>
      )}

      {isPending ? (
        <div className="grid gap-2">
          {Array.from({ length: 4 }, (_, i) => (
            <Skeleton key={i} className="h-20 w-full" />
          ))}
        </div>
      ) : isError && !data ? (
        <div className="flex flex-col items-start gap-3 rounded-lg border border-destructive/50 p-4">
          <p className="text-destructive text-sm">Couldn't load FAQs: {error.message}</p>
          <Button variant="outline" size="sm" onClick={() => refetch()}>
            Try again
          </Button>
        </div>
      ) : data.results.length === 0 ? (
        <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed p-10 text-center">
          <p className="font-medium">No FAQs yet</p>
          <p className="text-muted-foreground text-sm">Add the questions your customers ask most.</p>
          <Button variant="outline" onClick={() => setForm({ open: true })}>
            <Plus /> Add FAQ
          </Button>
        </div>
      ) : (
        <div className={isPlaceholderData ? 'opacity-60 transition-opacity' : undefined}>
          <ul className="divide-y rounded-md border">
            {data.results.map((faq) => (
              <li key={faq.id} className="flex items-start gap-4 p-4">
                <div className="grid min-w-0 flex-1 gap-1">
                  <p className="font-medium">{faq.question}</p>
                  <p className="text-muted-foreground line-clamp-3 text-sm whitespace-pre-line">{faq.answer}</p>
                </div>
                <div className="flex shrink-0">
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label={`Edit FAQ: ${faq.question}`}
                    onClick={() => setForm({ open: true, faq })}
                  >
                    <Pencil />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label={`Delete FAQ: ${faq.question}`}
                    onClick={() => {
                      setActionError(null)
                      setDeleting(faq)
                    }}
                  >
                    <Trash2 className="text-destructive" />
                  </Button>
                </div>
              </li>
            ))}
          </ul>
          <div className="mt-4">
            <PaginationControls
              page={page}
              pageSize={FAQS_PAGE_SIZE}
              count={data.count}
              onPageChange={setPage}
              disabled={isPlaceholderData}
            />
          </div>
        </div>
      )}

      <FaqFormDialog
        open={form.open}
        onOpenChange={(open) => !open && setForm({ open: false })}
        faq={form.open ? form.faq : undefined}
      />
      <DeleteFaqDialog
        faq={deleting}
        onOpenChange={(open) => !open && setDeleting(null)}
        onError={setActionError}
      />
    </div>
  )
}
