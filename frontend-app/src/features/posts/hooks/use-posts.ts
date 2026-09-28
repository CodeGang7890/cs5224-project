import { useQuery } from '@tanstack/react-query'

import type { ApiError } from '@/types/api'

import { getPost, getPosts } from '../api/posts-api'
import type { Post } from '../types'

// Query keys for this feature, kept together so invalidation stays consistent.
export const postKeys = {
  all: ['posts'] as const,
  list: (limit: number) => [...postKeys.all, 'list', limit] as const,
  detail: (id: number) => [...postKeys.all, 'detail', id] as const,
}

export function usePosts(limit = 10) {
  return useQuery<Post[], ApiError>({
    queryKey: postKeys.list(limit),
    queryFn: () => getPosts(limit),
  })
}

export function usePost(id: number) {
  return useQuery<Post, ApiError>({
    queryKey: postKeys.detail(id),
    queryFn: () => getPost(id),
    enabled: Number.isFinite(id),
  })
}
