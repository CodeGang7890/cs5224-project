import type { ReactNode } from 'react'

import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'

interface FormFieldProps {
  id: string
  label: string
  error?: string
  hint?: ReactNode
  /** Shows a "12 / 150" counter under the field. */
  length?: { current: number; max: number }
  required?: boolean
  className?: string
  children: ReactNode
}

/** Label + control + hint/error + optional character counter. */
export function FormField({ id, label, error, hint, length, required, className, children }: FormFieldProps) {
  const over = length && length.current > length.max
  return (
    <div className={cn('grid gap-2', className)}>
      <Label htmlFor={id}>
        {label}
        {required && <span className="text-destructive">*</span>}
      </Label>
      {children}
      {(error || hint || length) && (
        <div className="flex items-start justify-between gap-2 text-xs">
          <p id={`${id}-message`} className={error ? 'text-destructive' : 'text-muted-foreground'}>
            {error ?? hint}
          </p>
          {length && (
            <span className={cn('shrink-0 tabular-nums', over ? 'text-destructive' : 'text-muted-foreground')}>
              {length.current.toLocaleString()} / {length.max.toLocaleString()}
            </span>
          )}
        </div>
      )}
    </div>
  )
}
