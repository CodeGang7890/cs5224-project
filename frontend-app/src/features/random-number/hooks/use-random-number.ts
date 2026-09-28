import { useQuery } from '@tanstack/react-query'

import type { ApiError } from '@/types/api'

import { getRandomNumber } from '../api/random-number-api'
import type { RandomNumber } from '../types'

// Query keys for this feature, kept together so invalidation stays consistent.
export const randomNumberKeys = {
  all: ['random-number'] as const,
}

export function useRandomNumber() {
  return useQuery<RandomNumber, ApiError>({
    queryKey: randomNumberKeys.all,
    queryFn: getRandomNumber,
  })
}
