import { useSearchParams } from "react-router";

import {
  ORDER_STATUSES,
  type OrderSandboxFilter,
  type OrderStatus,
  type ScheduleListParams,
  type ScheduleOrdering,
} from "../types";
import { DEFAULT_PAGE_SIZE, PAGE_SIZES } from "./use-order-params";
import { useRememberedFilters } from "./use-remembered-filters";

// The Orders section's Services sub-tab (/orders/services) keeps its filters, sorting, paging and
// the open booking in the URL (`?status=…&booking=12`), like the orders list.

export const DEFAULT_SCHEDULE_ORDERING: ScheduleOrdering = "-start_time";
const DEFAULT_SANDBOX: OrderSandboxFilter = "include";

export const SCHEDULE_ORDERING_OPTIONS: {
  value: ScheduleOrdering;
  label: string;
}[] = [
  { value: "-start_time", label: "Latest time first" },
  { value: "start_time", label: "Earliest time first" },
  { value: "-created_time", label: "Newest booking first" },
  { value: "order_status", label: "Status" },
];

const SANDBOX_VALUES: OrderSandboxFilter[] = ["include", "exclude", "only"];

/** What's kept between visits (useRememberedFilters): filters, sorting and page size. */
const REMEMBERED = ["status", "sandbox", "ordering", "page_size"] as const;

export interface ScheduleFilterValues {
  status: OrderStatus | "";
  sandbox: OrderSandboxFilter;
  ordering: ScheduleOrdering;
  page: number;
  pageSize: number;
}

function readValues(params: URLSearchParams): ScheduleFilterValues {
  const status = params.get("status") as OrderStatus;
  const sandbox = params.get("sandbox") as OrderSandboxFilter;
  const ordering = params.get("ordering") as ScheduleOrdering;
  const page = Number(params.get("page"));
  const pageSize = Number(params.get("page_size"));
  return {
    status: ORDER_STATUSES.includes(status) ? status : "",
    sandbox: SANDBOX_VALUES.includes(sandbox) ? sandbox : DEFAULT_SANDBOX,
    ordering: SCHEDULE_ORDERING_OPTIONS.some((o) => o.value === ordering)
      ? ordering
      : DEFAULT_SCHEDULE_ORDERING,
    page: Number.isInteger(page) && page > 0 ? page : 1,
    pageSize: (PAGE_SIZES as readonly number[]).includes(pageSize)
      ? pageSize
      : DEFAULT_PAGE_SIZE,
  };
}

export function toScheduleListParams(
  values: ScheduleFilterValues,
): ScheduleListParams {
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
  ordering: DEFAULT_SCHEDULE_ORDERING,
  page_size: DEFAULT_PAGE_SIZE,
};

/** Filter, sort, paging and open-booking state of the bookings list, stored in the URL. */
export function useScheduleParams() {
  useRememberedFilters("orders-services", REMEMBERED);
  const [searchParams, setSearchParams] = useSearchParams();
  const values = readValues(searchParams);

  const setFilters = (changes: Partial<Omit<ScheduleFilterValues, "page">>) =>
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

  const openBookingId = Number(searchParams.get("booking")) || null;
  const setOpenBooking = (id: number | null) =>
    setSearchParams(
      (params) => {
        if (id === null) params.delete("booking");
        else params.set("booking", String(id));
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
    openBookingId,
    setOpenBooking,
  };
}
