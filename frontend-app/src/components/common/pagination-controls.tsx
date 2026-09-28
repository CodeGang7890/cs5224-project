import { ChevronLeft, ChevronRight } from 'lucide-react'

import { Button } from '@/components/ui/button'

interface PaginationControlsProps {
  page: number
  pageSize: number
  count: number
  onPageChange: (page: number) => void
  disabled?: boolean
}

/** "1–20 of 45" + previous/next buttons. Renders nothing when everything fits on one page. */
export function PaginationControls({ page, pageSize, count, onPageChange, disabled }: PaginationControlsProps) {
  const pageCount = Math.max(1, Math.ceil(count / pageSize))
  if (pageCount <= 1) return null

  const first = (page - 1) * pageSize + 1
  const last = Math.min(page * pageSize, count)

  return (
    <div className="flex items-center justify-between gap-4 text-sm">
      <span className="text-muted-foreground tabular-nums">
        {first}–{last} of {count}
      </span>
      <div className="flex items-center gap-2">
        <Button
          variant="outline"
          size="sm"
          onClick={() => onPageChange(page - 1)}
          disabled={disabled || page <= 1}
        >
          <ChevronLeft /> Previous
        </Button>
        <span className="tabular-nums">
          Page {page} of {pageCount}
        </span>
        <Button
          variant="outline"
          size="sm"
          onClick={() => onPageChange(page + 1)}
          disabled={disabled || page >= pageCount}
        >
          Next <ChevronRight />
        </Button>
      </div>
    </div>
  )
}
