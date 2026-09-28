# CLAUDE.md: frontend-app

Guidance for Claude Code when working in `frontend-app/`.

## What this is

**Ansera Business Admin**: a **client-side-only React SPA**. There is no SSR, no React Server Components, no Next.js/Remix and no framework mode. Don't add server-rendered patterns, `"use client"`/`"use server"` directives, or server-only APIs.

## Stack (keep to these; don't swap libraries without asking)

| Concern | Library | Notes |
| --- | --- | --- |
| Build | **Vite 8** | Not CRA. Config in `vite.config.ts` (React plugin + `@tailwindcss/vite`, `@` → `src` alias). |
| Language | **TypeScript 6** (strict-ish) | `verbatimModuleSyntax` is on, so use `import type` for type-only imports. Don't use `baseUrl` (deprecated in TS 6); `paths` alone defines the alias. |
| UI | **React 19** | Function components + hooks only. |
| Routing | **React Router v8** | Data router: route table in `src/app/routes.tsx`, `createBrowserRouter` in `src/app/router.tsx`, `RouterProvider` from `react-router/dom`. The URL is the source of truth: tabs are `NavLink`s, and UI such as modals that should survive refresh or back use search params (e.g. the profile modal uses `?profile`). Import hooks/components (`Link`, `NavLink`, `Outlet`, `useParams`, …) from `react-router`, **not** `react-router-dom`. |
| HTTP | **Axios** | Use a service client from `@/lib/api-client`, never bare `axios` or `fetch`. There is one client per backend service, built with `createApiClient(baseURL)`; currently `configurationApiClient` → `configuration-service` (Django, `VITE_CONFIGURATION_SERVICE_URL`, default `http://localhost:8000/api`, the API root). Paths are relative to `/api`: `/auth/…`, `/configuration/…`, `/products/`, `/faqs/`. The client also handles auth (see Authentication below). Interceptors normalise errors to `ApiError` (`@/types/api`), reading DRF's `detail` field. Django URLs end with `/`, so keep the trailing slash in request paths (e.g. `/configuration/random-number/`). |
| Server state | **TanStack Query v5** | All API data fetching goes through `useQuery`/`useMutation` for loading/error/caching. Use each feature's query-key factory (e.g. `postKeys`). Client config: `@/lib/query-client`. Devtools render in dev only. |
| Client state | **Zustand v5** | Only for client/UI state (theme, UI toggles, auth token, etc.). **Never** copy server data into Zustand; that's TanStack Query's job. Stores live in `src/stores/`, one per concern, named `use<Name>Store`. Select narrow slices: `useStore((s) => s.x)`. |
| Styling | **Tailwind CSS v4** | CSS-first config (no `tailwind.config.js`). Theme tokens are CSS variables in `src/index.css`. Dark mode uses the `.dark` class on `<html>`, set by `useApplyTheme`. |
| Components | **shadcn/ui** (Radix, `new-york` style, neutral) | Config in `components.json`. Components live in `src/components/ui/`. Add with `npx shadcn@latest add <name>`. Use the `cn()` helper from `@/lib/utils` to merge classes. Icons: `lucide-react`. |
| Lint | **oxlint** | `npm run lint`. Config in `.oxlintrc.json`. |

## Project structure conventions

- `src/app/`: app shell. `routes.tsx` is the route table (plain `RouteObject[]`, importable without a browser); `router.tsx` wraps it in `createBrowserRouter`; `providers.tsx` holds global providers.
- `src/config/`: `app.ts` (`APP_NAME`), `navigation.ts` (`paths` + top-nav `navItems`; use `paths` instead of hard-coded URLs), `env.ts` (typed env access).
- **Adding a page**: create `src/pages/<name>-page.tsx`, add its path to `paths`, add a route in `routes.tsx`, and add it to `navItems` if it's a top-nav tab. Pages set the browser tab title by rendering `<title>{`${title} | ${APP_NAME}`}</title>` (React 19 hoists it into `<head>`); `PagePlaceholder` does this already.
- `src/pages/`: route-level components. Keep them thin; they compose features. Current tabs (Home shows the random-number card; the rest use `PagePlaceholder`): Home `/`, Workflow `/workflow`, Product `/product`, Schedule `/schedule`, Payment `/payment`, FAQ `/faq`, Chats `/chats`, Chat Sandbox `/chat-sandbox`. 
- `src/features/<feature>/`: self-contained domain modules with `api/` (Axios functions), `hooks/` (TanStack Query hooks + keys), `components/`, `types.ts`, and an `index.ts` public API. Import features via `@/features/<feature>`, not their internal paths. `features/random-number` is the reference example for the Axios + TanStack Query pattern: it calls `GET /api/configuration/random-number/` on configuration-service and is shown on the Home page. `features/auth` holds the login dialog, auth API calls and the `useAuth` / `useCurrentUser` hooks. `features/profile` holds the profile modal (`ProfileDialog`), which shows `useCurrentUser()` data.
- `src/components/ui/`: shadcn-generated code. Prefer composing or wrapping over heavy edits. The oxlint `only-export-components` rule is disabled for this folder.
- `src/components/layout/`: layout components. `RootLayout` renders the sticky header (app name, nav tabs, theme toggle, `AuthControls`) and the `<Outlet />`. `AuthControls` lives in layout, not in a feature, because it combines `features/auth` and `features/profile`; this avoids a circular import.
- `src/components/common/`: shared app-level components that aren't shadcn primitives (e.g. `PagePlaceholder`).
- `src/lib/`: shared singletons/utilities (`createApiClient` + service clients, `queryClient`, `cn`).
- `src/stores/`: Zustand stores. `src/hooks/`: shared hooks. `src/types/`: shared types.
- File names are **kebab-case** (`random-number-card.tsx`, `use-random-number.ts`), matching shadcn. Exports are named (no default exports).
- Always import from `src` via the `@/` alias.

## Authentication (JWT from configuration-service)

- **Backend endpoints:**
  - `POST /api/auth/token/`: `{username, password}` → `{access, refresh}`.
  - `POST /api/auth/token/refresh/`: `{refresh}` → `{access, refresh}`. Refresh tokens **rotate**, and the old one is blacklisted.
  - `POST /api/auth/logout/`: `{refresh}` blacklists it.
  - `GET /api/auth/me/` → `CurrentUser` (`id`, `username`, `email`, names, `business` id | null, `business_name`, `is_staff`, `is_superuser`).
  - Lifetimes: access 15 minutes, refresh 7 days.
- **Tokens** live in `useAuthStore` (`src/stores/auth-store.ts`, Zustand `persist` → localStorage key `auth`). A `storage` event listener rehydrates it, so tabs stay in sync. "Logged in" means a refresh token is present (`selectIsAuthenticated`).
- **`createApiClient` handles auth for every request, so never add auth headers or refresh logic in feature code:**
  - The request interceptor adds `Authorization: Bearer <access>`.
  - On a 401, the response interceptor calls `refreshAccessToken()`, which is single-flight via a shared promise. It uses bare `axios`, so it bypasses the interceptors. It then retries the request once (`_retriedAfterRefresh`).
  - If the refresh fails, it calls `clearTokens()` and rejects with the original 401.
  - Pass `{ skipAuth: true }` for requests that must not carry or refresh tokens (login/logout).
  - The `skipAuth` and `_retriedAfterRefresh` config fields are declared by module augmentation in `api-client.ts`.
- **Component API:** `useAuth()` from `@/features/auth` returns `{ isAuthenticated, user, isLoadingUser, login, isLoggingIn, loginError, resetLoginError, logout }`. `useCurrentUser()` is the `/me` query (key `authKeys.currentUser`).
- **Cache safety:** `useResetQueriesOnAuthChange()` (mounted in `AppProviders` via `GlobalEffects`) resets all queries on any login or logout, including an expired session or another tab. It excludes the current-user query, because `login()` fetches that itself and resetting would cancel it. On logout, the current-user query is removed. Keep this behaviour when changing auth.
- **Retries:** `queryClient` doesn't retry 4xx errors (`shouldRetry`), so a 401 or 403 isn't retried pointlessly.
- **Not built yet:** route guards or redirects for protected pages, an "expired session" toast, and role-based UI.

## Environment variables

- Must start with `VITE_`. Read them through `env` in `@/config/env`, not `import.meta.env` directly.
- When adding one, update `.env.example`, `src/vite-env.d.ts` and `src/config/env.ts`.
- Current: `VITE_CONFIGURATION_SERVICE_URL` (configuration-service API root; default `http://localhost:8000/api`).

## Commands

```bash
npm install      # install deps
npm run dev      # dev server (http://localhost:5173)
npm run build    # tsc -b + vite build → dist/
npm run preview  # serve the production build
npm run lint     # oxlint
```

Before finishing a change, run `npm run build` and `npm run lint`. Both must pass.

## Environment notes for Claude

- The shadcn CLI needs `ui.shadcn.com`, which the Apple Claude Code sandbox blocks by default, so `npx shadcn add` fails until the user allows that domain. If it's blocked, write the component source by hand into `src/components/ui/`, following the existing files.
- The sandbox also blocks listening on local ports, so `npm run dev` / `preview` can't be smoke-tested from inside Claude. Use `npm run build` to verify.
