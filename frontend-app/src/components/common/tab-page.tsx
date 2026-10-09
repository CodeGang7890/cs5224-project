import type { ReactNode } from 'react'

import { APP_NAME } from '@/config/app'

interface TabPageProps {
  /** The sub-tab, e.g. "Products". */
  title: string
  /** The section it's in, e.g. "Catalog" (for the browser tab title). */
  section: string
  description?: ReactNode
  children: ReactNode
}

/** Body of a section's sub-tab (under `SectionLayout`, which shows the heading and the sub-tabs). */
export function TabPage({ title, section, description, children }: TabPageProps) {
  return (
    <div className="flex flex-col gap-6">
      <title>{`${title} · ${section} | ${APP_NAME}`}</title>
      {description && <p className="text-muted-foreground -mt-2 text-sm">{description}</p>}
      {children}
    </div>
  )
}
