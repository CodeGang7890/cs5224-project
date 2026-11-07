export interface LoginCredentials {
  username: string;
  password: string;
}

/** POST /api/auth/signup/: a new account (no business yet: it's created next). */
export interface SignUpInput {
  username: string;
  email: string;
  password: string;
  first_name: string;
  last_name: string;
}

/** The account's plan (configuration-service `auth_app.SubscriptionTier`); nothing is billed yet. */
export type SubscriptionTier = "free" | "starter" | "growth" | "business";

export const SUBSCRIPTION_TIER_LABELS: Record<SubscriptionTier, string> = {
  free: "Free",
  starter: "Starter",
  growth: "Growth",
  business: "Business",
};

/** Response of GET /api/auth/me/ */
export interface CurrentUser {
  id: number;
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  /** ID of the BusinessConfiguration the account belongs to (null for e.g. the admin superuser). */
  business: number | null;
  business_name: string | null;
  subscription_tier: SubscriptionTier;
  is_staff: boolean;
  is_superuser: boolean;
}
