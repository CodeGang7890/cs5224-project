// Subscription plans: prices (excluding VAT), included AI interactions and features from the Final Report's
// business model (Table 2), plus a few more of the app's features. The account's own plan is
// `CurrentUser.subscription_tier` (GET /api/auth/me/). Hardcoded here: there's no billing yet.

import type { SubscriptionTier } from "@/features/auth";

export type PlanId = SubscriptionTier;

export interface Plan {
  id: PlanId;
  name: string;
  tagline: string;
  /** Monthly price in Singapore dollars (0: free). */
  price: number;
  usage: string;
  features: string[];
  recommended?: boolean;
}

export const PLANS: Plan[] = [
  {
    id: "free",
    name: "Free",
    tagline: "Set up your assistant and test it.",
    price: 0,
    usage: "Up to ~50 customer interactions/month",
    features: [
      "Products, services and FAQs",
      "Workflow: welcome message, reply style and details to collect",
      "Unlimited test chats in the Chat Sandbox",
      "1 WhatsApp number",
    ],
  },
  {
    id: "starter",
    name: "Starter",
    tagline: "For a small shop going live.",
    price: 10.99,
    usage: "300 AI interactions/month",
    features: [
      "1 WhatsApp number, connected with Facebook",
      "No-code workflow builder",
      "24/7 AI replies from your catalog and FAQs",
      "Orders with live stock and bookings in free time slots",
      "Invoices and receipts",
      "Xendit payment links, payment and reminder follow-ups",
      "Customers check their order status in the chat",
      "CRM up to 1,000 contacts",
      "6 months of chat history",
    ],
  },
  {
    id: "growth",
    name: "Growth",
    tagline: "For a growing team.",
    price: 35.99,
    usage: "1,500 AI interactions/month",
    features: [
      "Everything in Starter, plus:",
      "3 staff logins",
      "CRM up to 10,000 contacts",
      "12 months of chat history",
      "Analytics dashboard",
      "Unanswered questions inbox: answer once, then add it to your FAQs",
      "Several service providers with weekly schedules",
      "Your own custom reply style",
    ],
    recommended: true,
  },
  {
    id: "business",
    name: "Business",
    tagline: "For busy businesses and bigger teams.",
    price: 106.99,
    usage: "4,000 AI interactions/month",
    features: [
      "Everything in Growth, plus:",
      "10 staff logins",
      "3 WhatsApp numbers",
      "CRM up to 50,000 contacts",
      "Bulk schedule tools: add slots, copy weeks ahead",
      "Sandbox debug view: see how each reply was decided",
      "Priority support",
    ],
  },
];

/** The plan with this id (Free for an unknown one). */
export function planFor(id: PlanId | undefined) {
  return PLANS.find((plan) => plan.id === id) ?? PLANS[0];
}

/** Position in PLANS: higher is more expensive. */
export function planRank(id: PlanId) {
  return PLANS.findIndex((plan) => plan.id === id);
}

export function formatPrice(amount: number) {
  return amount === 0 ? "Free" : `S$${amount.toFixed(2)}`;
}
