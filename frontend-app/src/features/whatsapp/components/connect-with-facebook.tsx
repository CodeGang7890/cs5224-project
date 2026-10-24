import { useEffect, useState } from "react";

import { ConfirmDialog } from "@/components/common/confirm-dialog";
import { FacebookIcon } from "@/components/common/brand-icons";
import { Button } from "@/components/ui/button";
import {
  EmbeddedSignupError,
  isEmbeddedSignupConfigured,
  loadFacebookSdk,
  startEmbeddedSignup,
} from "@/lib/facebook-sdk";
import { apiErrorMessage } from "@/lib/form-errors";
import type { ApiError } from "@/types/api";

import { useConnectWithEmbeddedSignup } from "../hooks/use-whatsapp-configuration";

function errorMessage(error: unknown): string {
  return error instanceof EmbeddedSignupError
    ? error.message
    : apiErrorMessage(error as ApiError);
}

/**
 * "Connect with Facebook": WhatsApp Embedded Signup. After the confirmation, Meta's popup opens (from
 * the confirm click itself, so it isn't blocked); when the business finishes, its code and account IDs
 * go straight to the backend, which connects WhatsApp and sets up the webhook. `replacing`: reconnect
 * (replaces the current connection). Until Embedded Signup is configured (`VITE_META_APP_ID` /
 * `VITE_META_CONFIG_ID`), the button shows but does nothing.
 */
export function ConnectWithFacebook({
  replacing = false,
}: {
  replacing?: boolean;
}) {
  const connect = useConnectWithEmbeddedSignup();
  const [sdkReady, setSdkReady] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [inPopup, setInPopup] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Load the SDK early: the popup must open straight from the click.
  useEffect(() => {
    if (!isEmbeddedSignupConfigured) return;
    let active = true;
    loadFacebookSdk().then(
      () => active && setSdkReady(true),
      (err: Error) => active && setError(err.message),
    );
    return () => {
      active = false;
    };
  }, []);

  const handleConfirm = () => {
    setError(null);
    setInPopup(true);
    startEmbeddedSignup() // opens Meta's popup now, within the click
      .then((result) =>
        // The code expires after 30 seconds: send it at once.
        connect.mutateAsync({
          code: result.code,
          waba_id: result.wabaId,
          phone_number_id: result.phoneNumberId,
        }),
      )
      .then(() => setConfirmOpen(false))
      .catch((err: unknown) => {
        setConfirmOpen(false);
        if (!(err instanceof EmbeddedSignupError && err.kind === "cancelled"))
          setError(errorMessage(err));
      })
      .finally(() => setInPopup(false));
  };

  const isPending = inPopup || connect.isPending;

  return (
    <>
      <div className="flex flex-col items-start gap-2">
        <Button
          type="button"
          variant={replacing ? "outline" : "default"}
          className={
            replacing ? undefined : "bg-[#1877F2] text-white hover:bg-[#166FE5]"
          }
          disabled={(isEmbeddedSignupConfigured && !sdkReady) || isPending}
          onClick={() => {
            if (!isEmbeddedSignupConfigured) return; // not hooked up yet
            setError(null);
            setConfirmOpen(true);
          }}
        >
          <FacebookIcon />
          {isEmbeddedSignupConfigured && !sdkReady
            ? "Loading Facebook…"
            : replacing
              ? "Reconnect with Facebook"
              : "Connect with Facebook"}
        </Button>
        {error && (
          <p role="alert" className="text-destructive text-sm">
            {error}
          </p>
        )}
      </div>

      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title={
          replacing ? "Reconnect WhatsApp?" : "Connect WhatsApp with Facebook?"
        }
        description={
          <>
            A Facebook window opens: log in, choose or create your WhatsApp
            Business account, and add and verify your business phone number.
            When you finish, we connect it and set up messages automatically.
            {replacing && " This replaces your current WhatsApp connection."}
          </>
        }
        confirmLabel="Continue to Facebook"
        pendingLabel={
          connect.isPending ? "Connecting…" : "Waiting for Facebook…"
        }
        isPending={isPending}
        onConfirm={handleConfirm}
      />
    </>
  );
}
