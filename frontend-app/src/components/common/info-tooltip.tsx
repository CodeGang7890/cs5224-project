import type { ReactNode } from 'react'
import { Info } from 'lucide-react'

import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'

interface InfoTooltipProps {
  /** What the tooltip explains, for screen readers (e.g. "Description"). */
  label: string
  children: ReactNode
}

/** A small (i) button that shows an explanation on hover or keyboard focus. */
export function InfoTooltip({ label, children }: InfoTooltipProps) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          aria-label={`About ${label}`}
          className="text-muted-foreground hover:text-foreground focus-visible:ring-ring/50 rounded-full outline-none focus-visible:ring-[3px]"
        >
          <Info className="size-3.5" />
        </button>
      </TooltipTrigger>
      <TooltipContent side="top" className="max-w-xs text-left">
        {children}
      </TooltipContent>
    </Tooltip>
  )
}
