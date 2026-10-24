import { env } from "@/config/env";

// WhatsApp Embedded Signup: Meta's popup where a business logs in with Facebook, picks or creates its
// WhatsApp Business account and verifies its number. It returns a single-use code (valid for 30 s) through
// FB.login's callback, and the account IDs through a `WA_EMBEDDED_SIGNUP` message event. Both go to
// configuration-service, which does the rest (`connectWithEmbeddedSignup` in `@/features/whatsapp`).
//
// Meta only runs it on HTTPS pages of the domains set on our app, so it doesn't work on localhost.
// Docs: developers.facebook.com/documentation/business-messaging/whatsapp/embedded-signup/implementation

interface FacebookLoginResponse {
  authResponse?: { code?: string } | null;
  status?: string;
}

interface FacebookSdk {
  init(options: {
    appId: string;
    autoLogAppEvents: boolean;
    xfbml: boolean;
    version: string;
  }): void;
  login(
    callback: (response: FacebookLoginResponse) => void,
    options: Record<string, unknown>,
  ): void;
}

declare global {
  interface Window {
    FB?: FacebookSdk;
    fbAsyncInit?: () => void;
  }
}

export const isEmbeddedSignupConfigured = Boolean(
  env.meta.appId && env.meta.configId,
);

export interface EmbeddedSignupResult {
  code: string;
  wabaId: string;
  phoneNumberId: string;
}

export type EmbeddedSignupErrorKind =
  "cancelled" | "no_phone_number" | "not_ready" | "failed";

export class EmbeddedSignupError extends Error {
  readonly kind: EmbeddedSignupErrorKind;

  constructor(kind: EmbeddedSignupErrorKind, message: string) {
    super(message);
    this.kind = kind;
  }
}

interface SignupEvent {
  type: "WA_EMBEDDED_SIGNUP";
  event: string;
  data?: {
    waba_id?: string;
    phone_number_id?: string;
    current_step?: string;
    error_message?: string;
  };
}

/** How long to wait for the account IDs after the code (both come when the popup finishes). */
const SESSION_INFO_WAIT_MS = 5_000;

let sdk: Promise<FacebookSdk> | null = null;
let ready: FacebookSdk | null = null;

/** Loads and initialises the Facebook SDK once. Call it early (e.g. when the button shows). */
export function loadFacebookSdk(): Promise<FacebookSdk> {
  sdk ??= new Promise<FacebookSdk>((resolve, reject) => {
    window.fbAsyncInit = () => {
      window.FB!.init({
        appId: env.meta.appId,
        autoLogAppEvents: true,
        xfbml: true,
        version: env.meta.graphApiVersion,
      });
      ready = window.FB!;
      resolve(ready);
    };
    const script = document.createElement("script");
    script.src = "https://connect.facebook.net/en_US/sdk.js";
    script.async = true;
    script.defer = true;
    script.crossOrigin = "anonymous";
    script.onerror = () => {
      sdk = null; // try again next time
      reject(
        new EmbeddedSignupError(
          "not_ready",
          "Couldn't load Facebook. Check your connection or ad blocker.",
        ),
      );
    };
    document.body.appendChild(script);
  });
  return sdk;
}

function parseSignupEvent(event: MessageEvent): SignupEvent | null {
  let host: string;
  try {
    host = new URL(event.origin).hostname;
  } catch {
    return null;
  }
  if (host !== "facebook.com" && !host.endsWith(".facebook.com")) return null;
  try {
    const data =
      typeof event.data === "string" ? JSON.parse(event.data) : event.data;
    return data?.type === "WA_EMBEDDED_SIGNUP" ? (data as SignupEvent) : null;
  } catch {
    return null; // the SDK posts other, non-JSON messages too
  }
}

/**
 * Opens Meta's Embedded Signup popup. **Call it directly in a click handler**: browsers block popups
 * opened later, so the SDK must already be loaded (`loadFacebookSdk`). Resolves with the code and IDs
 * once the business finishes; rejects with an `EmbeddedSignupError` otherwise.
 */
export function startEmbeddedSignup(): Promise<EmbeddedSignupResult> {
  const fb = ready;
  if (!isEmbeddedSignupConfigured || !fb) {
    return Promise.reject(
      new EmbeddedSignupError(
        "not_ready",
        "Facebook is still loading. Try again in a moment.",
      ),
    );
  }

  return new Promise<EmbeddedSignupResult>((resolve, reject) => {
    let code: string | null = null;
    let finished: SignupEvent | null = null;
    let cancelled: SignupEvent | null = null;
    let waitTimer: ReturnType<typeof setTimeout> | undefined;

    const done = (outcome: () => void) => {
      window.removeEventListener("message", onMessage);
      clearTimeout(waitTimer);
      outcome();
    };

    const settle = () => {
      if (!code || !finished) return;
      const { waba_id: wabaId, phone_number_id: phoneNumberId } =
        finished.data ?? {};
      if (!wabaId || !phoneNumberId) {
        done(() =>
          reject(
            new EmbeddedSignupError(
              "no_phone_number",
              "No phone number was added. Connect again and add your business phone number in the Facebook window.",
            ),
          ),
        );
        return;
      }
      const result = { code, wabaId, phoneNumberId };
      done(() => resolve(result));
    };

    const onMessage = (event: MessageEvent) => {
      const signup = parseSignupEvent(event);
      if (!signup) return;
      if (signup.event.startsWith("FINISH")) finished = signup;
      else cancelled = signup;
      settle();
    };
    window.addEventListener("message", onMessage);

    // FB.login needs a plain (not async) function as its callback.
    fb.login(
      (response) => {
        const receivedCode = response.authResponse?.code;
        if (!receivedCode) {
          const reported = cancelled?.data?.error_message;
          done(() =>
            reject(
              reported
                ? new EmbeddedSignupError("failed", reported)
                : new EmbeddedSignupError(
                    "cancelled",
                    "The Facebook window was closed before finishing.",
                  ),
            ),
          );
          return;
        }
        code = receivedCode;
        settle();
        if (!finished) {
          waitTimer = setTimeout(
            () =>
              done(() =>
                reject(
                  new EmbeddedSignupError(
                    "failed",
                    "Facebook didn't send your WhatsApp account details. Please try again.",
                  ),
                ),
              ),
            SESSION_INFO_WAIT_MS,
          );
        }
      },
      {
        config_id: env.meta.configId,
        response_type: "code",
        override_default_response_type: true,
        extras: { setup: {} },
      },
    );
  });
}
