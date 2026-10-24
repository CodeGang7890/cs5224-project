import type { ReactNode } from 'react'
import { TriangleAlert } from 'lucide-react'
import { Link, useLocation } from 'react-router'

import { Button } from '@/components/ui/button'
import { paths } from '@/config/navigation'
import { cn } from '@/lib/utils'
import { selectIsAuthenticated, useAuthStore } from '@/stores/auth-store'

import { reconnectMessage } from '../expiry'
import { useWhatsAppConfiguration } from '../hooks/use-whatsapp-configuration'
import type { WhatsAppConfiguration } from '../types'

/** The token expiry warning on the WhatsApp card (above its Reconnect button); nothing while active. */
export function ReconnectNotice({ config }: { config: WhatsAppConfiguration }) {
  const message = reconnectMessage(config)
  if (!message) return null
  return <AlertBox expired={config.access_token_status === 'expired'}>{message}</AlertBox>
}

/**
 * App-wide banner (RootLayout) while the business's WhatsApp token is expiring or expired, linking to
 * the WhatsApp card on Home (which shows its own notice, so the banner is hidden there).
 */
export function WhatsAppReconnectAlert() {
  const isAuthenticated = useAuthStore(selectIsAuthenticated)
  const { pathname } = useLocation()
  const { data: config } = useWhatsAppConfiguration(isAuthenticated)
  const message = isAuthenticated && config ? reconnectMessage(config) : null
  if (!config || !message || pathname === paths.home) return null
  return (
    <AlertBox expired={config.access_token_status === 'expired'}>
      <span className="flex-1">{message}</span>
      <Button size="sm" variant="outline" asChild>
        <Link to={paths.home}>Reconnect</Link>
      </Button>
    </AlertBox>
  )
}

function AlertBox({ expired, children }: { expired: boolean; children: ReactNode }) {
  return (
    <div
      role="alert"
      className={cn(
        'flex flex-wrap items-center gap-3 rounded-xl border p-3 text-sm',
        expired ? 'border-destructive/50 bg-destructive/10' : 'border-amber-500/50 bg-amber-500/10',
      )}
    >
      <TriangleAlert
        className={cn('size-4 shrink-0', expired ? 'text-destructive' : 'text-amber-600 dark:text-amber-400')}
      />
      {children}
    </div>
  )
}
