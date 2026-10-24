import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import type { ApiError } from "@/types/api";

import {
  getChatConfiguration,
  getReplyStyles,
  saveChatConfiguration,
} from "../api/chat-configuration-api";
import type {
  ChatConfiguration,
  ChatConfigurationInput,
  ReplyStyle,
} from "../types";

export const chatConfigurationKeys = {
  all: ["chat-configuration"] as const,
  detail: () => [...chatConfigurationKeys.all, "detail"] as const,
  replyStyles: () => [...chatConfigurationKeys.all, "reply-styles"] as const,
};

/** The settings of the chat flow's steps (the defaults until the business saves its own). */
export function useChatConfiguration() {
  return useQuery<ChatConfiguration, ApiError>({
    queryKey: chatConfigurationKeys.detail(),
    queryFn: getChatConfiguration,
  });
}

/** Saves the configuration (PUT) and puts the saved one straight into the cache. */
export function useSaveChatConfiguration() {
  const queryClient = useQueryClient();
  return useMutation<ChatConfiguration, ApiError, ChatConfigurationInput>({
    mutationFn: saveChatConfiguration,
    onSuccess: (saved) =>
      queryClient.setQueryData(chatConfigurationKeys.detail(), saved),
  });
}

/** The reply styles to choose from (they only change with a backend release). */
export function useReplyStyles() {
  return useQuery<ReplyStyle[], ApiError>({
    queryKey: chatConfigurationKeys.replyStyles(),
    queryFn: getReplyStyles,
    staleTime: Infinity,
  });
}
