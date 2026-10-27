// Mirrors configuration-service chat_app/questions.py. The backend validates too.

/** How the answer is sent to the customer in the chat (questions.ANSWER_MESSAGE_PREFIX). */
export function answerMessage(question: string, answer: string): string {
  return `Regarding your previous question about "${question}": ${answer}`;
}

export const QUESTION_LIMITS = {
  /** FAQ question length (product_app FAQ_QUESTION_MAX_LENGTH). */
  questionMaxLength: 300,
  /** So the chat message (prefix + question + answer) fits in 4,096 characters (ANSWER_MAX_LENGTH). */
  answerMaxLength: 3753,
} as const;
