import { ChevronLeft, ChevronRight, CircleAlert } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import type { DetailedPaginated } from "@/types/api";

import { PAGE_SIZES } from "../hooks/use-order-params";

// Shared by the Orders tab's lists (orders and bookings).

export function FilterSelect({
  id,
  label,
  value,
  onChange,
  options,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: { value: string; label: string }[];
}) {
  return (
    <div className="grid gap-1.5">
      <Label htmlFor={id} className="text-muted-foreground text-xs font-normal">
        {label}
      </Label>
      <NativeSelect
        id={id}
        className="w-48"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </NativeSelect>
    </div>
  );
}

export function PaginationBar<T>({
  id,
  noun,
  data,
  disabled,
  onPageChange,
  onPageSizeChange,
}: {
  /** id of the page size select. */
  id: string;
  /** Singular, e.g. "order". */
  noun: string;
  data: DetailedPaginated<T>;
  disabled: boolean;
  onPageChange: (page: number) => void;
  onPageSizeChange: (pageSize: number) => void;
}) {
  const first = (data.current_page - 1) * data.page_size + 1;
  const last = first + data.results.length - 1;
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 text-sm">
      <div className="flex items-center gap-3">
        <span className="text-muted-foreground tabular-nums">
          {first}–{last} of {data.count} {noun}
          {data.count === 1 ? "" : "s"}
        </span>
        <div className="flex items-center gap-2">
          <Label
            htmlFor={id}
            className="text-muted-foreground text-xs font-normal"
          >
            Per page
          </Label>
          <NativeSelect
            id={id}
            className="w-20"
            value={data.page_size}
            onChange={(event) => onPageSizeChange(Number(event.target.value))}
          >
            {PAGE_SIZES.map((size) => (
              <option key={size} value={size}>
                {size}
              </option>
            ))}
          </NativeSelect>
        </div>
      </div>
      <div className="flex items-center gap-2">
        <Button
          variant="outline"
          size="sm"
          disabled={disabled || !data.has_previous}
          onClick={() => onPageChange(data.current_page - 1)}
        >
          <ChevronLeft /> Previous
        </Button>
        <span className="tabular-nums">
          Page {data.current_page} of {data.total_pages}
        </span>
        <Button
          variant="outline"
          size="sm"
          disabled={disabled || !data.has_next}
          onClick={() => onPageChange(data.current_page + 1)}
        >
          Next <ChevronRight />
        </Button>
      </div>
    </div>
  );
}

export function ErrorState({
  noun,
  status,
  message,
  onRetry,
  onFirstPage,
}: {
  /** Plural, e.g. "orders". */
  noun: string;
  status?: number;
  message: string;
  onRetry: () => void;
  onFirstPage: () => void;
}) {
  // 403: no business; 404: a page past the end (e.g. an old link).
  const text =
    status === 403
      ? `Your account isn't linked to a business, so there are no ${noun} to show.`
      : status === 404
        ? "That page doesn't exist any more."
        : `Couldn't load ${noun}: ${message}`;
  return (
    <div className="border-destructive/50 flex flex-col items-start gap-3 rounded-xl border p-4">
      <p className="text-destructive flex items-center gap-2 text-sm">
        <CircleAlert className="size-4" /> {text}
      </p>
      {status === 404 ? (
        <Button variant="outline" size="sm" onClick={onFirstPage}>
          Go to the first page
        </Button>
      ) : (
        status !== 403 && (
          <Button variant="outline" size="sm" onClick={() => onRetry()}>
            Try again
          </Button>
        )
      )}
    </div>
  );
}
