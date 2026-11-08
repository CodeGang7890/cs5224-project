// Subscription plans: prices and usage from the Preliminary Report's business model, features limited to
// what the app does today. The account's own plan is `CurrentUser.subscription_tier` (GET /api/auth/me/).
// Hardcoded here: there's no billing yet.

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
    price: 7.99,
    usage: "Up to ~300 customer interactions/month",
    features: [
      "1 WhatsApp number, connected with Facebook",
      "24/7 AI replies from your catalog and FAQs",
      "Product orders with live stock",
      "Appointment bookings in free time slots",
      "Xendit payment links and payment tracking",
      "Customers check their order status in the chat",
      "Full conversation history",
    ],
  },
  {
    id: "growth",
    name: "Growth",
    tagline: "For a growing team.",
    price: 21.99,
    usage: "Up to ~1,500 interactions/month",
    features: [
      "Everything in Starter, plus:",
      "Unanswered questions inbox: answer once, then add it to your FAQs",
      "Several service providers with weekly schedules",
      "Your own custom reply style",
      "Conversation search and filters",
      "Up to 3 team logins",
    ],
    recommended: true,
  },
  {
    id: "business",
    name: "Business",
    tagline: "For busy businesses and bigger teams.",
    price: 49.99,
    usage: "Higher / custom usage",
    features: [
      "Everything in Growth, plus:",
      "Up to 10 team logins",
      "Bulk schedule tools: add slots, copy weeks ahead",
      "Sandbox debug view: see how each reply was decided",
      "Dedicated support: a personal contact and priority help",
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
