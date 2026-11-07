/** Normalised error shape thrown by the API client for every failed request. */
export interface ApiError {
  message: string;
  status?: number;
  data?: unknown;
}

/** DRF PageNumberPagination response (list endpoints, 20 items per page). */
export interface Paginated<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

/** configuration-service `DetailedPageNumberPagination` (lists with `page` + `page_size`). */
export interface DetailedPaginated<T> extends Paginated<T> {
  total_pages: number;
  current_page: number;
  page_size: number;
  has_next: boolean;
  has_previous: boolean;
}
