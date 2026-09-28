# CLAUDE.md: frontend-app

Guidance for Claude Code when working in `frontend-app/`.

## What this is

A **client-side-only React SPA**. There is no SSR, no React Server Components, no Next.js/Remix and no framework mode. Don't add server-rendered patterns, `"use client"`/`"use server"` directives, or server-only APIs.

## Stack (keep to these; don't swap libraries without asking)

| Concern | Library | Notes |
| --- | --- | --- |
| Build | **Vite 8** | Not CRA. Config in `vite.config.ts` (React plugin + `@tailwindcss/vite`, `@` → `src` alias). |
| Language | **TypeScript 6** (strict-ish) | `verbatimModuleSyntax` is on, so use `import type` for type-only imports. Don't use `baseUrl` (deprecated in TS 6); `paths` alone defines the alias. |
| UI | **React 19** | Function components + hooks only. |
| Routing | **React Router v8** | Data router: `createBrowserRouter` in `src/app/router.tsx`, `RouterProvider` from `react-router/dom`. Import hooks/components (`Link`, `NavLink`, `Outlet`, `useParams`, …) from `react-router`, **not** `react-router-dom`. |
| HTTP | **Axios** | Always use the shared `apiClient` from `@/lib/api-client`, never bare `axios` or `fetch`. Its interceptors normalise errors to `ApiError` (`@/types/api`). |
| Server state | **TanStack Query v5** | All API data fetching goes through `useQuery`/`useMutation` for loading/error/caching. Use each feature's query-key factory (e.g. `postKeys`). Client config: `@/lib/query-client`. Devtools render in dev only. |
| Client state | **Zustand v5** | Only for client/UI state (theme, UI toggles, auth token, etc.). **Never** copy server data into Zustand; that's TanStack Query's job. Stores live in `src/stores/`, one per concern, named `use<Name>Store`. Select narrow slices: `useStore((s) => s.x)`. |
| Styling | **Tailwind CSS v4** | CSS-first config (no `tailwind.config.js`). Theme tokens are CSS variables in `src/index.css`. Dark mode uses the `.dark` class on `<html>`, set by `useApplyTheme`. |
| Components | **shadcn/ui** (Radix, `new-york` style, neutral) | Config in `components.json`. Components live in `src/components/ui/`. Add with `npx shadcn@latest add <name>`. Use the `cn()` helper from `@/lib/utils` to merge classes. Icons: `lucide-react`. |
| Lint | **oxlint** | `npm run lint`. Config in `.oxlintrc.json`. |

## Project structure conventions

- `src/app/`: app shell (root component, global providers, route table). Register new routes in `router.tsx` and global providers in `providers.tsx`.
- `src/pages/`: route-level components. Keep them thin; they compose features.
- `src/features/<feature>/`: self-contained domain modules with `api/` (Axios functions), `hooks/` (TanStack Query hooks + keys), `components/`, `types.ts`, and an `index.ts` public API. Import features via `@/features/<feature>`, not their internal paths. `features/posts` is the reference example (it calls the JSONPlaceholder demo API) and can be deleted once real features exist.
- `src/components/ui/`: shadcn-generated code. Prefer composing or wrapping over heavy edits. The oxlint `only-export-components` rule is disabled for this folder.
- `src/components/layout/`: layout components (`RootLayout` renders header/nav + `<Outlet />`).
- `src/lib/`: shared singletons/utilities (`apiClient`, `queryClient`, `cn`).
- `src/stores/`: Zustand stores. `src/hooks/`: shared hooks. `src/types/`: shared types. `src/config/env.ts`: typed env access.
- File names are **kebab-case** (`post-list.tsx`, `use-posts.ts`), matching shadcn. Exports are named (no default exports).
- Always import from `src` via the `@/` alias.

## Environment variables

- Must start with `VITE_`. Read them through `env` in `@/config/env`, not `import.meta.env` directly.
- When adding one, update `.env.example`, `src/vite-env.d.ts` and `src/config/env.ts`.
- Current: `VITE_API_BASE_URL` (Axios base URL; defaults to the JSONPlaceholder demo API).

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
