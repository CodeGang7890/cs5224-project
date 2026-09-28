import { configurationApiClient } from '@/lib/api-client'
import type { Paginated } from '@/types/api'

import type { Faq, FaqInput } from '../types'

// Plain async functions that call configuration-service. Lists are scoped to the logged-in
// user's business by the backend; `business` is never sent (it defaults to yours).

export async function listFaqs(page: number): Promise<Paginated<Faq>> {
  const { data } = await configurationApiClient.get<Paginated<Faq>>('/faqs/', { params: { page } })
  return data
}

export async function createFaq(input: FaqInput): Promise<Faq> {
  const { data } = await configurationApiClient.post<Faq>('/faqs/', input)
  return data
}

export async function updateFaq(id: number, changes: Partial<FaqInput>): Promise<Faq> {
  const { data } = await configurationApiClient.patch<Faq>(`/faqs/${id}/`, changes)
  return data
}

export async function deleteFaq(id: number): Promise<void> {
  await configurationApiClient.delete(`/faqs/${id}/`)
}
