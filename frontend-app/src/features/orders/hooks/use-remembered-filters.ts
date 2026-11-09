import { useEffect, useRef } from "react";
import { useSearchParams } from "react-router";

const STORAGE_PREFIX = "ansera:filters:";

function readSaved(key: string): Record<string, string> {
  try {
    const value: unknown = JSON.parse(
      localStorage.getItem(STORAGE_PREFIX + key) ?? "{}",
    );
    return value && typeof value === "object"
      ? (value as Record<string, string>)
      : {};
  } catch {
    return {};
  }
}

/**
 * Keeps a list page's filters and sorting (the URL search params in `names`) across visits: they're saved
 * in localStorage under `key` whenever they change, and put back into the URL when the page is opened
 * without any of them (e.g. from its tab, whose link has no query string). A URL that has some of them
 * wins, so shared links still work. Paging and the open dialog aren't remembered.
 */
export function useRememberedFilters(key: string, names: readonly string[]) {
  const [searchParams, setSearchParams] = useSearchParams();
  const restored = useRef(false);

  useEffect(() => {
    if (restored.current) return;
    restored.current = true;
    if (names.some((name) => searchParams.has(name))) return;
    const saved = readSaved(key);
    const entries = names
      .filter((name) => typeof saved[name] === "string")
      .map((name) => [name, saved[name]] as const);
    if (entries.length === 0) return;
    setSearchParams(
      (params) => {
        for (const [name, value] of entries) params.set(name, value);
        return params;
      },
      { replace: true },
    );
    // Only on the page's first render: afterwards the URL is the source of truth.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const snapshot = names
    .map((name) => `${name}=${searchParams.get(name) ?? ""}`)
    .join("&");
  useEffect(() => {
    if (!restored.current) return;
    const current: Record<string, string> = {};
    for (const name of names) {
      const value = searchParams.get(name);
      if (value !== null) current[name] = value;
    }
    try {
      localStorage.setItem(STORAGE_PREFIX + key, JSON.stringify(current));
    } catch {
      // Storage full or disabled: the filters just aren't remembered.
    }
    // `snapshot` covers every value read here.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, snapshot]);
}
