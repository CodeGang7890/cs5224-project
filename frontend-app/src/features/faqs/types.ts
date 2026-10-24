/** An FAQ as returned by configuration-service (`/api/faqs/`). */
export interface Faq {
  id: number;
  business: number;
  question: string;
  answer: string;
}

/** Fields users may write. `id` and `business` (defaults to your business) are read-only. */
export type FaqInput = Pick<Faq, "question" | "answer">;
