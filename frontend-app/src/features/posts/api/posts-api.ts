import { apiClient } from '@/lib/api-client'

import type { Post } from '../types'

// Plain async functions that call the API. No React here, so they're easy to reuse and test.

export async function getPosts(limit = 10): Promise<Post[]> {
  const { data } = await apiClient.get<Post[]>('/posts', { params: { _limit: limit } })
  return data
}

export async function getPost(id: number): Promise<Post> {
  const { data } = await apiClient.get<Post>(`/posts/${id}`)
  return data
}
