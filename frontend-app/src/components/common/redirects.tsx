import { Navigate, useLocation } from 'react-router'

/** Redirects to `to`, keeping the current query string and hash (for old URLs). */
export function RedirectKeepingSearch({ to }: { to: string }) {
  const { search, hash } = useLocation()
  return <Navigate to={{ pathname: to, search, hash }} replace />
}

interface SectionIndexRedirectProps {
  /** The section's default sub-tab. */
  to: string
  /** Old `?tab=<value>` URLs of the section → their sub-tab now. */
  legacyTabs?: Record<string, string>
}

/**
 * Index route of a section: goes to its default sub-tab, or for an old `?tab=` URL (e.g.
 * `/orders?tab=services&booking=4`), to that sub-tab with the other parameters kept.
 */
export function SectionIndexRedirect({ to, legacyTabs = {} }: SectionIndexRedirectProps) {
  const { search, hash } = useLocation()
  const params = new URLSearchParams(search)
  const tab = params.get('tab')
  params.delete('tab')
  const rest = params.toString()
  const pathname = (tab !== null && legacyTabs[tab]) || to
  return <Navigate to={{ pathname, search: rest ? `?${rest}` : '', hash }} replace />
}
