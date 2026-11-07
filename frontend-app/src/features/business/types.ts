// Mirrors configuration-service configuration_app (BusinessConfigurationSerializer).

/** The logged-in user's own business (GET / PUT /configuration/business/). */
export interface Business {
  id: number;
  business_name: string;
  location: string;
  description: string;
  payment_expiry_minutes: number;
}

/** What PUT /configuration/business/ takes: creates the business (a new account) or updates it. */
export type BusinessInput = Omit<Business, "id" | "payment_expiry_minutes"> & {
  payment_expiry_minutes?: number;
};

// configuration_app.models limits.
export const BUSINESS_LIMITS = {
  business_name: 150,
  location: 255,
  description: 2000,
} as const;
