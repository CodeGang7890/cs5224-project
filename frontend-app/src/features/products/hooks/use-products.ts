import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import type { ApiError, Paginated } from '@/types/api'

import { createProduct, deleteProduct, listProducts, updateProduct } from '../api/products-api'
import type { Product, ProductInput } from '../types'

export const PRODUCTS_PAGE_SIZE = 20 // matches the backend's PAGE_SIZE

export const productKeys = {
  all: ['products'] as const,
  list: (page: number) => [...productKeys.all, 'list', page] as const,
  hasActive: () => [...productKeys.all, 'has-active'] as const,
}

export function useProducts(page: number) {
  return useQuery<Paginated<Product>, ApiError>({
    queryKey: productKeys.list(page),
    queryFn: () => listProducts(page),
    placeholderData: keepPreviousData, // keep the table visible while changing page
  })
}

export type SaveProductVariables =
  | { id?: undefined; input: ProductInput }
  | { id: number; input: Partial<ProductInput> }

/** Creates (no `id`) or updates (with `id`) a product, then refreshes the lists. */
export function useSaveProduct() {
  const queryClient = useQueryClient()
  return useMutation<Product, ApiError, SaveProductVariables>({
    mutationFn: ({ id, input }) =>
      id === undefined ? createProduct(input as ProductInput) : updateProduct(id, input),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: productKeys.all }),
  })
}

export function useDeleteProduct() {
  const queryClient = useQueryClient()
  return useMutation<void, ApiError, number>({
    mutationFn: deleteProduct,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: productKeys.all }),
  })
}

/**
 * Whether the business has at least one active product, i.e. whether customers can order in the
 * chat (the backend only offers active products). Reads the pages until it finds one.
 */
export function useHasActiveProducts() {
  return useQuery<boolean, ApiError>({
    queryKey: productKeys.hasActive(),
    queryFn: async () => {
      for (let page = 1; ; page++) {
        const data = await listProducts(page)
        if (data.results.some((product) => product.is_active)) return true
        if (!data.next) return false
      }
    },
  })
}
