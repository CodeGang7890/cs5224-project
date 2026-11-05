// How often the Catalog and Orders lists re-fetch on their own (short polling: other services write
// orders, bookings and payments, so the data can change without this app doing anything). TanStack
// Query pauses it while the browser tab is hidden. The sections' Refresh button fetches at once.
export const LIVE_REFRESH_INTERVAL_MS = 15_000;
