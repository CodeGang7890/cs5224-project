import { useSearchParams } from "react-router";

import {
  ORDER_STATUSES,
  type OrderListParams,
  type OrderOrdering,
  type OrderSandboxFilter,
  type OrderStatus,
} from "../types";

// The Orders tab keeps its filters, sorting, paging and the open order in the URL (like Chats).

export const PAGE_SIZES = [10, 20, 50, 100] as const;
export const DEFAULT_PAGE_SIZE = 20;
export const DEFAULT_ORDERING: OrderOrdering = "-created_time";
export const DEFAULT_SANDBOX: OrderSandboxFilter = "include";

export const ORDERING_OPTIONS: { value: OrderOrdering; label: string }[] = [
  { value: "-created_time", label: "Newest first" },
  { value: "created_time", label: "Oldest first" },
  { value: "order_status", label: "Status" },
];

const SANDBOX_VALUES: OrderSandboxFilter[] = ["include", "exclude", "only"];

export interface OrderFilterValues {
  status: OrderStatus | "";
  sandbox: OrderSandboxFilter;
  ordering: OrderOrdering;
  page: number;
  pageSize: number;
}

function readValues(params: URLSearchParams): OrderFilterValues {
  const status = params.get("status") as OrderStatus;
  const sandbox = params.get("sandbox") as OrderSandboxFilter;
  const ordering = params.get("ordering") as OrderOrdering;
  const page = Number(params.get("page"));
  const pageSize = Number(params.get("page_size"));
  return {
    status: ORDER_STATUSES.includes(status) ? status : "",
    sandbox: SANDBOX_VALUES.includes(sandbox) ? sandbox : DEFAULT_SANDBOX,
    ordering: ORDERING_OPTIONS.some((o) => o.value === ordering)
      ? ordering
      : DEFAULT_ORDERING,
    page: Number.isInteger(page) && page > 0 ? page : 1,
    pageSize: (PAGE_SIZES as readonly number[]).includes(pageSize)
      ? pageSize
      : DEFAULT_PAGE_SIZE,
  };
}

export function toListParams(values: OrderFilterValues): OrderListParams {
  return {
    page: values.page,
    page_size: values.pageSize,
    ordering: values.ordering,
    sandbox: values.sandbox,
    order_status: values.status || undefined,
  };
}

const DEFAULTS: Record<string, string | number> = {
  status: "",
  sandbox: DEFAULT_SANDBOX,
  ordering: DEFAULT_ORDERING,
  page_size: DEFAULT_PAGE_SIZE,
};

/** Filter, sort, paging and open-order state of the Orders tab, stored in the URL. */
export function useOrderParams() {
  const [searchParams, setSearchParams] = useSearchParams();
  const values = readValues(searchParams);

  /** Changes filters/sorting/page size; goes back to page 1. Defaults are left out of the URL. */
  const setFilters = (changes: Partial<Omit<OrderFilterValues, "page">>) =>
    setSearchParams(
      (params) => {
        for (const [key, value] of Object.entries(changes)) {
          const name = key === "pageSize" ? "page_size" : key;
          if (value === DEFAULTS[name]) params.delete(name);
          else params.set(name, String(value));
        }
        params.delete("page");
        return params;
      },
      { replace: true },
    );

  const setPage = (page: number) =>
    setSearchParams(
      (params) => {
        if (page <= 1) params.delete("page");
        else params.set("page", String(page));
        return params;
      },
      { replace: true },
    );

  const clearFilters = () =>
    setFilters({ status: "", sandbox: DEFAULT_SANDBOX });
  const hasFilters = values.status !== "" || values.sandbox !== DEFAULT_SANDBOX;

  const openOrderId = Number(searchParams.get("order")) || null;
  const setOpenOrder = (id: number | null) =>
    setSearchParams(
      (params) => {
        if (id === null) params.delete("order");
        else params.set("order", String(id));
        return params;
      },
      { replace: true },
    );

  return {
    values,
    setFilters,
    setPage,
    clearFilters,
    hasFilters,
    openOrderId,
    setOpenOrder,
  };
}
