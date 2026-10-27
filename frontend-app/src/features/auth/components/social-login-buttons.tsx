import { useEffect, useState } from "react";

import { FacebookIcon, GoogleIcon } from "@/components/common/brand-icons";
import { Button } from "@/components/ui/button";
import {
  isSocialLoginConfigured,
  loadFirebaseAuth,
  SocialLoginError,
  type SocialProvider,
} from "@/lib/firebase";
import { apiErrorMessage } from "@/lib/form-errors";
import type { ApiError } from "@/types/api";

import { useAuth } from "../hooks/use-auth";

function errorMessage(error: unknown): string {
  return error instanceof SocialLoginError
    ? error.message
    : apiErrorMessage(error as ApiError);
}

/**
 * "Continue with Google / Facebook" (Identity Platform): logs in, or signs up on the first time. Until it's
 * configured (`VITE_FIREBASE_*`), the buttons show but do nothing (like Connect with Facebook).
 */
export function SocialLoginButtons({ onLoggedIn }: { onLoggedIn: () => void }) {
  const { loginWithProvider, pendingProvider } = useAuth();
  const [error, setError] = useState<string | null>(null);

  // Load the SDK now, so the popup opens straight from the click.
  useEffect(() => {
    if (isSocialLoginConfigured) loadFirebaseAuth().catch(() => undefined);
  }, []);

  const handleClick = (provider: SocialProvider) => {
    if (!isSocialLoginConfigured) return; // not set up yet
    setError(null);
    loginWithProvider(provider).then(onLoggedIn, (err: unknown) => {
      if (!(err instanceof SocialLoginError && err.kind === "cancelled"))
        setError(errorMessage(err));
    });
  };

  return (
    <div className="grid gap-2">
      <Button
        type="button"
        variant="outline"
        disabled={Boolean(pendingProvider)}
        onClick={() => handleClick("google")}
      >
        <GoogleIcon />
        {pendingProvider === "google"
          ? "Waiting for Google…"
          : "Continue with Google"}
      </Button>
      <Button
        type="button"
        variant="outline"
        disabled={Boolean(pendingProvider)}
        onClick={() => handleClick("facebook")}
      >
        <FacebookIcon className="text-[#1877F2]" />
        {pendingProvider === "facebook"
          ? "Waiting for Facebook…"
          : "Continue with Facebook"}
      </Button>
      {error && (
        <p role="alert" className="text-destructive text-sm">
          {error}
        </p>
      )}
    </div>
  );
}
