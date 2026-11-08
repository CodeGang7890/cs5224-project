import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from "@tanstack/react-query";

import { chatSessionKeys } from "@/features/chat-sessions";
import { type Faq, faqKeys } from "@/features/faqs";
import type { ApiError, DetailedPaginated } from "@/types/api";

import {
  addQuestionToFaqs,
  answerQuestion,
  dismissQuestion,
  listQuestions,
} from "../api/questions-api";
import type {
  AnswerQuestionInput,
  QuestionListParams,
  UnansweredQuestion,
} from "../types";

export const QUESTIONS_PAGE_SIZE = 20;
/** How often the open-question count (the Chats tab's alert) is re-checked. */
const OPEN_COUNT_REFRESH_MS = 60_000;

export const questionKeys = {
  all: ["unanswered-questions"] as const,
  list: (params: QuestionListParams) =>
    [...questionKeys.all, "list", params] as const,
  openCount: () => [...questionKeys.all, "open-count"] as const,
};

export function useQuestions(params: QuestionListParams) {
  return useQuery<DetailedPaginated<UnansweredQuestion>, ApiError>({
    queryKey: questionKeys.list(params),
    queryFn: () => listQuestions(params),
    placeholderData: keepPreviousData,
  });
}

/** How many questions are waiting for an answer (polled, for the alert). */
export function useOpenQuestionCount() {
  return useQuery<DetailedPaginated<UnansweredQuestion>, ApiError, number>({
    queryKey: questionKeys.openCount(),
    queryFn: () => listQuestions({ status: "open", page: 1, page_size: 1 }),
    select: (data) => data.count,
    refetchInterval: OPEN_COUNT_REFRESH_MS,
  });
}

function refreshAfterChange(queryClient: QueryClient) {
  return Promise.all([
    queryClient.invalidateQueries({ queryKey: questionKeys.all }),
    // Answering adds a chat message.
    queryClient.invalidateQueries({ queryKey: chatSessionKeys.all }),
  ]);
}

export function useAnswerQuestion() {
  const queryClient = useQueryClient();
  return useMutation<
    UnansweredQuestion,
    ApiError,
    { id: number; input: AnswerQuestionInput }
  >({
    mutationFn: ({ id, input }) => answerQuestion(id, input),
    onSuccess: () => refreshAfterChange(queryClient),
  });
}

/** Adds an answered question to the FAQs (the question itself doesn't change). */
export function useAddQuestionToFaqs() {
  const queryClient = useQueryClient();
  return useMutation<Faq, ApiError, number>({
    mutationFn: addQuestionToFaqs,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: faqKeys.all }),
  });
}

export function useDismissQuestion() {
  const queryClient = useQueryClient();
  return useMutation<UnansweredQuestion, ApiError, number>({
    mutationFn: dismissQuestion,
    onSuccess: () => refreshAfterChange(queryClient),
  });
}
