import { configurationApiClient } from '@/lib/api-client'

import type { RandomNumber } from '../types'

// Plain async functions that call the API. No React here, so they're easy to reuse and test.

export async function getRandomNumber(): Promise<RandomNumber> {
  const { data } = await configurationApiClient.get<RandomNumber>('/random-number/')
  return data
}
