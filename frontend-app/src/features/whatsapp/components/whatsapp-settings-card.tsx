import { useState } from "react";
import {
  CircleAlert,
  CircleCheck,
  ExternalLink,
  MessageCircle,
  Phone,
  Unplug,
} from "lucide-react";

import { ConfirmDialog } from "@/components/common/confirm-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { AuthDialog } from "@/features/auth";
import { selectIsAuthenticated, useAuthStore } from "@/stores/auth-store";

import {
  useDeleteWhatsAppConfiguration,
  useWhatsAppConfiguration,
} from "../hooks/use-whatsapp-configuration";
import type { WhatsAppConfiguration } from "../types";
import { formatDateTime, HEALTH_BADGES } from "../health";
import { ConnectWithFacebook } from "./connect-with-facebook";
import { ReconnectNotice } from "./reconnect-alert";

/**
 * Connects the business's WhatsApp Business number with Facebook (Meta's Embedded Signup), which also
 * sets up its webhook, so there's nothing to enter by hand. Connected: the number, Reconnect, Disconnect.
 */
export function WhatsAppSettingsCard() {
  const isAuthenticated = useAuthStore(selectIsAuthenticated);
  const {
    data: config,
    isPending,
    isError,
    error,
    refetch,
  } = useWhatsAppConfiguration(isAuthenticated);

  return (
    <Card className="max-w-2xl">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <MessageCircle className="size-5" /> WhatsApp
        </CardTitle>
        <CardDescription>
          Connect your WhatsApp Business number, so customers' messages reach
          your assistant.
        </CardDescription>
        {isAuthenticated && !isPending && !isError && (
          <CardAction>
            {config ? (
              <Badge
                variant="outline"
                className={HEALTH_BADGES[config.health].className}
              >
                {HEALTH_BADGES[config.health].label}
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
            <p className="text-muted-foreground text-sm">
              Log in to connect WhatsApp.
            </p>
            <AuthDialog />
          </div>
        ) : isPending ? (
          <div className="grid gap-3">
            <Skeleton className="h-9 w-full" />
            <Skeleton className="h-9 w-48" />
          </div>
        ) : isError ? (
          error.status === 403 ? (
            <p className="text-muted-foreground text-sm">
              Your account isn't linked to a business, so it can't connect
              WhatsApp.
            </p>
          ) : (
            <div className="flex flex-col items-start gap-3">
              <p className="text-destructive text-sm">
                Couldn't load your WhatsApp settings: {error.message}
              </p>
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
              Log in with Facebook, choose or create your WhatsApp Business
              account and verify your number. We set up the rest.
            </p>
            <ConnectWithFacebook />
          </div>
        )}
      </CardContent>
    </Card>
  );
}

/** The connected number, what (if anything) to do about it (`health`), and Reconnect / Disconnect. */
function Connection({ config }: { config: WhatsAppConfiguration }) {
  const viaFacebook = config.connection_method === "embedded_signup";
  return (
    <div className="grid gap-4">
      <ConnectedNumber config={config} />
      {config.health === "disconnected" || config.health === "banned" ? (
        <StatusAlert config={config} />
      ) : config.health !== "ok" ? (
        <ReconnectNotice config={config} />
      ) : (
        <p className="flex items-start gap-2 text-sm">
          <CircleCheck className="mt-0.5 size-4 shrink-0 text-emerald-600 dark:text-emerald-400" />
          {viaFacebook
            ? "Connected with Facebook. Customers' messages reach your assistant automatically: there's nothing to set up in Meta."
            : "Connected with your own Meta app. Reconnect with Facebook to let us manage the connection for you."}
        </p>
      )}
      {viaFacebook && (
        <p className="text-muted-foreground text-xs">
          {config.health === "ok" && config.access_token_expires_time && (
            <>
              Facebook's access lasts until{" "}
              {formatDateTime(config.access_token_expires_time)}: we'll remind
              you before then, so you can reconnect to renew it.{" "}
            </>
          )}
          WhatsApp Business account {config.waba_id}. Meta charges for some
          conversations: add a payment method in{" "}
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
  );
}

/** Meta reported the connection disconnected or banned: why, and what to do. */
function StatusAlert({ config }: { config: WhatsAppConfiguration }) {
  const since = config.status_updated_time
    ? ` (${formatDateTime(config.status_updated_time)})`
    : "";
  return (
    <div
      role="alert"
      className="border-destructive/50 bg-destructive/10 flex items-start gap-2 rounded-xl border p-3 text-sm"
    >
      <CircleAlert className="text-destructive mt-0.5 size-4 shrink-0" />
      <div className="grid gap-1">
        <p className="font-medium">
          {config.health === "banned"
            ? "Meta banned this WhatsApp account"
            : "WhatsApp is disconnected"}
          {since}
        </p>
        <p>{config.status_reason}</p>
        <p className="text-muted-foreground">
          {config.health === "banned"
            ? "Your assistant can't reply to customers on WhatsApp until Meta reinstates the account."
            : "Customers' messages no longer reach your assistant. Reconnect with Facebook to fix it."}
        </p>
      </div>
    </div>
  );
}

/** The number Meta confirmed when it was connected: shows the owner which number is connected. */
function ConnectedNumber({ config }: { config: WhatsAppConfiguration }) {
  return (
    <div className="flex items-center gap-3 rounded-lg border px-4 py-3">
      <Phone className="text-muted-foreground size-4 shrink-0" />
      <div className="grid gap-0.5">
        <p className="text-sm font-medium">
          {[config.display_phone_number, config.verified_name]
            .filter(Boolean)
            .join(" · ") || config.phone_number_id}
        </p>
        <p className="text-muted-foreground text-xs">
          Connected number, as verified by Meta
        </p>
      </div>
    </div>
  );
}

function DisconnectButton() {
  const deleteConfig = useDeleteWhatsAppConfiguration();
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleConfirm = () => {
    setError(null);
    deleteConfig.mutate(undefined, {
      onSuccess: () => setConfirmOpen(false),
      onError: (err) => {
        setConfirmOpen(false);
        setError(`Couldn't disconnect: ${err.message}`);
      },
    });
  };

  return (
    <>
      <div className="flex flex-col items-end gap-1">
        <Button
          type="button"
          variant="outline"
          onClick={() => setConfirmOpen(true)}
        >
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
  );
}
