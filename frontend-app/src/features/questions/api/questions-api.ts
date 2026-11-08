import type { Faq } from "@/features/faqs";
import { configurationApiClient } from "@/lib/api-client";
import type { DetailedPaginated } from "@/types/api";

import type {
  AnswerQuestionInput,
  QuestionListParams,
  UnansweredQuestion,
} from "../types";

// The backend scopes everything to the logged-in user's business (403 for another business's question).

export async function listQuestions(
  params: QuestionListParams,
): Promise<DetailedPaginated<UnansweredQuestion>> {
  const { data } = await configurationApiClient.get<
    DetailedPaginated<UnansweredQuestion>
  >("/chat/questions/", { params });
  return data;
}

/** Sends the answer in the customer's chat and marks the question answered (with its answer). */
export async function answerQuestion(
  id: number,
  input: AnswerQuestionInput,
): Promise<UnansweredQuestion> {
  const { data } = await configurationApiClient.post<UnansweredQuestion>(
    `/chat/questions/${id}/answer/`,
    input,
  );
  return data;
}

/** Adds an answered question to the business's FAQs: a new FAQ with its question and answer. */
export async function addQuestionToFaqs(id: number): Promise<Faq> {
  const { data } = await configurationApiClient.post<Faq>(
    `/chat/questions/${id}/add-to-faqs/`,
  );
  return data;
}

/** Closes the question without replying. */
export async function dismissQuestion(id: number): Promise<UnansweredQuestion> {
  const { data } = await configurationApiClient.post<UnansweredQuestion>(
    `/chat/questions/${id}/dismiss/`,
  );
  return data;
}
