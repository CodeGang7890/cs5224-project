import { useSearchParams } from "react-router";

/** Current list page from the URL (`?page=2`), so pages are shareable and survive refresh. */
export function usePageParam() {
  const [searchParams, setSearchParams] = useSearchParams();
  const raw = Number(searchParams.get("page"));
  const page = Number.isInteger(raw) && raw > 0 ? raw : 1;

  const setPage = (next: number) => {
    setSearchParams(
      (params) => {
        if (next <= 1) params.delete("page");
        else params.set("page", String(next));
        return params;
      },
      { replace: true },
    );
  };

  return [page, setPage] as const;
}
