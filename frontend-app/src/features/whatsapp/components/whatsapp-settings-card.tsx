import { useState } from 'react'
import { CircleCheck, ExternalLink, MessageCircle, Phone, Unplug } from 'lucide-react'

import { ConfirmDialog } from '@/components/common/confirm-dialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { LoginDialog } from '@/features/auth'
import { selectIsAuthenticated, useAuthStore } from '@/stores/auth-store'

import { useDeleteWhatsAppConfiguration, useWhatsAppConfiguration } from '../hooks/use-whatsapp-configuration'
import type { WhatsAppConfiguration } from '../types'
import { ConnectWithFacebook } from './connect-with-facebook'

/**
 * Connects the business's WhatsApp Business number with Facebook (Meta's Embedded Signup), which also
 * sets up its webhook, so there's nothing to enter by hand. Connected: the number, Reconnect, Disconnect.
 */
export function WhatsAppSettingsCard() {
  const isAuthenticated = useAuthStore(selectIsAuthenticated)
  const { data: config, isPending, isError, error, refetch } = useWhatsAppConfiguration(isAuthenticated)
  const isConnected = Boolean(config)

  return (
    <Card className="max-w-2xl">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <MessageCircle className="size-5" /> WhatsApp
        </CardTitle>
        <CardDescription>
          Connect your WhatsApp Business number, so customers' messages reach your assistant.
        </CardDescription>
        {isAuthenticated && !isPending && !isError && (
          <CardAction>
            {isConnected ? (
              <Badge variant="outline" className="border-emerald-500/50 text-emerald-700 dark:text-emerald-400">
                Connected
              </Badge>
            ) : (
              <Badge variant="outline">Not connected</Badge>
            )}
          </CardAction>
        )}
      </CardHeader>
      <CardContent>
        {!isAuthenticated ? (
          <div className="flex flex-wrap items-center gap-3">
            <p className="text-muted-foreground text-sm">Log in to connect WhatsApp.</p>
            <LoginDialog />
          </div>
        ) : isPending ? (
          <div className="grid gap-3">
            <Skeleton className="h-9 w-full" />
            <Skeleton className="h-9 w-48" />
          </div>
        ) : isError ? (
          error.status === 403 ? (
            <p className="text-muted-foreground text-sm">
              Your account isn't linked to a business, so it can't connect WhatsApp.
            </p>
          ) : (
            <div className="flex flex-col items-start gap-3">
              <p className="text-destructive text-sm">Couldn't load your WhatsApp settings: {error.message}</p>
              <Button variant="outline" size="sm" onClick={() => refetch()}>
                Try again
              </Button>
            </div>
          )
        ) : config ? (
          <Connection config={config} />
        ) : (
          <div className="grid gap-3">
            <p className="text-sm">
              Log in with Facebook, choose or create your WhatsApp Business account and verify your number. We set up the
              rest.
            </p>
            <ConnectWithFacebook />
          </div>
        )}
      </CardContent>
    </Card>
  )
}

/** The connected number, and Reconnect / Disconnect. */
function Connection({ config }: { config: WhatsAppConfiguration }) {
  const viaFacebook = config.connection_method === 'embedded_signup'
  return (
    <div className="grid gap-4">
      <ConnectedNumber config={config} />
      <p className="flex items-start gap-2 text-sm">
        <CircleCheck className="mt-0.5 size-4 shrink-0 text-emerald-600 dark:text-emerald-400" />
        {viaFacebook
          ? "Connected with Facebook. Customers' messages reach your assistant automatically: there's nothing to set up in Meta."
          : 'Connected with your own Meta app. Reconnect with Facebook to let us manage the connection for you.'}
      </p>
      {viaFacebook && (
        <p className="text-muted-foreground text-xs">
          WhatsApp Business account {config.waba_id}. Meta charges for some conversations: add a payment method in{' '}
          <a
            href="https://business.facebook.com/wa/manage/home/"
            target="_blank"
            rel="noreferrer"
            className="text-primary inline-flex items-center gap-0.5 font-medium underline-offset-4 hover:underline"
          >
            WhatsApp Manager
            <ExternalLink className="size-3" aria-hidden="true" />
          </a>
          .
        </p>
      )}
      <div className="flex flex-wrap items-start justify-between gap-2">
        <ConnectWithFacebook replacing />
        <DisconnectButton />
      </div>
    </div>
  )
}

/** The number Meta confirmed when it was connected: shows the owner which number is connected. */
function ConnectedNumber({ config }: { config: WhatsAppConfiguration }) {
  return (
    <div className="flex items-center gap-3 rounded-lg border px-4 py-3">
      <Phone className="text-muted-foreground size-4 shrink-0" />
      <div className="grid gap-0.5">
        <p className="text-sm font-medium">
          {[config.display_phone_number, config.verified_name].filter(Boolean).join(' · ') || config.phone_number_id}
        </p>
        <p className="text-muted-foreground text-xs">Connected number, as verified by Meta</p>
      </div>
    </div>
  )
}

function DisconnectButton() {
  const deleteConfig = useDeleteWhatsAppConfiguration()
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleConfirm = () => {
    setError(null)
    deleteConfig.mutate(undefined, {
      onSuccess: () => setConfirmOpen(false),
      onError: (err) => {
        setConfirmOpen(false)
        setError(`Couldn't disconnect: ${err.message}`)
      },
    })
  }

  return (
    <>
      <div className="flex flex-col items-end gap-1">
        <Button type="button" variant="outline" onClick={() => setConfirmOpen(true)}>
          <Unplug /> Disconnect
        </Button>
        {error && (
          <p role="alert" className="text-destructive text-xs">
            {error}
          </p>
        )}
      </div>
      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title="Disconnect WhatsApp?"
        description="Customers' messages will no longer reach your assistant. You can connect again with Facebook later."
        confirmLabel="Disconnect"
        pendingLabel="Disconnecting…"
        destructive
        isPending={deleteConfig.isPending}
        onConfirm={handleConfirm}
      />
    </>
  )
}
