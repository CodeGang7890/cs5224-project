import { configurationApiClient } from "@/lib/api-client";
import type { Paginated } from "@/types/api";

import type { Product, ProductInput } from "../types";

// Plain async functions that call configuration-service. Lists are scoped to the logged-in
// user's business by the backend; `business` is never sent (it defaults to yours).

export async function listProducts(page: number): Promise<Paginated<Product>> {
  const { data } = await configurationApiClient.get<Paginated<Product>>(
    "/products/",
    {
      params: { page },
    },
  );
  return data;
}

export async function createProduct(input: ProductInput): Promise<Product> {
  const { data } = await configurationApiClient.post<Product>(
    "/products/",
    input,
  );
  return data;
}

export async function updateProduct(
  id: number,
  changes: Partial<ProductInput>,
): Promise<Product> {
  const { data } = await configurationApiClient.patch<Product>(
    `/products/${id}/`,
    changes,
  );
  return data;
}

export async function deleteProduct(id: number): Promise<void> {
  await configurationApiClient.delete(`/products/${id}/`);
}
