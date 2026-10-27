import type { Auth } from "firebase/auth";

import { env } from "@/config/env";

// Logging in with Google or Facebook through Google Cloud Identity Platform (Firebase Authentication).
// The provider's popup gives an Identity Platform ID token, which goes to configuration-service
// (POST /auth/firebase/, `loginWithProvider` in `@/features/auth`) for our usual JWT pair. Firebase is
// signed out straight away: our JWTs are the only session.
//
// The SDK is loaded on demand (preload it when the login UI shows: `loadFirebaseAuth`), so it isn't in
// the main bundle and the popup can open straight from the click (popup blockers).

export type SocialProvider = "google" | "facebook";

export const isSocialLoginConfigured = Boolean(
  env.firebase.apiKey && env.firebase.authDomain && env.firebase.projectId,
);

export type SocialLoginErrorKind = "cancelled" | "account_exists" | "failed";

export class SocialLoginError extends Error {
  readonly kind: SocialLoginErrorKind;

  constructor(kind: SocialLoginErrorKind, message: string) {
    super(message);
    this.kind = kind;
  }
}

let authPromise: Promise<{
  auth: Auth;
  sdk: typeof import("firebase/auth");
}> | null = null;

/** Loads and initialises the Firebase Auth SDK once. */
export function loadFirebaseAuth() {
  if (!isSocialLoginConfigured)
    return Promise.reject(new SocialLoginError("failed", "Not configured."));
  authPromise ??= Promise.all([
    import("firebase/app"),
    import("firebase/auth"),
  ]).then(([app, sdk]) => {
    const firebaseApp = app.getApps()[0] ?? app.initializeApp(env.firebase);
    return { auth: sdk.getAuth(firebaseApp), sdk };
  });
  authPromise.catch(() => {
    authPromise = null; // e.g. offline: try again next time
  });
  return authPromise;
}

function errorFor(error: unknown): SocialLoginError {
  const code = (error as { code?: string }).code ?? "";
  if (
    code === "auth/popup-closed-by-user" ||
    code === "auth/cancelled-popup-request" ||
    code === "auth/user-cancelled"
  ) {
    return new SocialLoginError("cancelled", "Cancelled.");
  }
  if (code === "auth/account-exists-with-different-credential") {
    return new SocialLoginError(
      "account_exists",
      "This email already logs in with another provider. Use that one (e.g. Google) instead.",
    );
  }
  if (code === "auth/popup-blocked") {
    return new SocialLoginError(
      "failed",
      "Your browser blocked the login window. Allow pop-ups and try again.",
    );
  }
  if (code === "auth/unauthorized-domain") {
    return new SocialLoginError(
      "failed",
      "This site isn't allowed to log in with Google / Facebook yet.",
    );
  }
  return new SocialLoginError("failed", "Couldn't log in. Please try again.");
}

/** Runs the provider's popup and returns the Identity Platform ID token. Call it from the click. */
export async function signInWithProvider(
  provider: SocialProvider,
): Promise<string> {
  const { auth, sdk } = await loadFirebaseAuth();
  const authProvider =
    provider === "google"
      ? new sdk.GoogleAuthProvider()
      : new sdk.FacebookAuthProvider();
  if (provider === "google")
    authProvider.setCustomParameters({ prompt: "select_account" });
  else authProvider.addScope("email");
  try {
    const { user } = await sdk.signInWithPopup(auth, authProvider);
    return await user.getIdToken();
  } catch (error) {
    throw errorFor(error);
  } finally {
    await sdk.signOut(auth).catch(() => undefined);
  }
}
