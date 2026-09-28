# Frontend App

A client-side single-page app (SPA) built with React, TypeScript and Vite. It has no server rendering and no server components.

## Tech stack

| Concern | Library |
| --- | --- |
| Build tool / dev server | [Vite](https://vite.dev) |
| UI framework | [React](https://react.dev) + TypeScript |
| Routing | [React Router](https://reactrouter.com) (data router, `createBrowserRouter`) |
| HTTP client | [Axios](https://axios-http.com) |
| Server state (loading / error / caching) | [TanStack Query](https://tanstack.com/query) |
| Client state | [Zustand](https://zustand.docs.pmnd.rs) |
| Styling | [Tailwind CSS v4](https://tailwindcss.com) |
| UI components | [shadcn/ui](https://ui.shadcn.com) (Radix primitives, `lucide-react` icons) |
| Linting | [oxlint](https://oxc.rs) |

## Prerequisites

- **Node.js 20.19+** (or 22.12+); Vite 8 needs one of these. Check with `node -v`.
- **npm** (comes with Node).

## Getting started

```bash
cd frontend-app
npm install                 # install dependencies
cp .env.example .env.local  # optional: configure environment variables
npm run dev                 # start the dev server
```

Then open the URL Vite prints, usually <http://localhost:5173>.

## Scripts

| Command | What it does |
| --- | --- |
| `npm run dev` | Starts the dev server with hot module reload |
| `npm run build` | Type-checks (`tsc -b`) and builds for production into `dist/` |
| `npm run preview` | Serves the production build locally so you can check it |
| `npm run lint` | Lints the code with oxlint |

## Environment variables

Vite only exposes variables that start with `VITE_`. Put local values in `.env.local`, which git ignores.

| Variable | Description | Default |
| --- | --- | --- |
| `VITE_API_BASE_URL` | Base URL used by the Axios client | `https://jsonplaceholder.typicode.com` (demo API) |

When you add a variable, add it to `.env.example`, `src/vite-env.d.ts` (types) and `src/config/env.ts`.

## Project structure

```
frontend-app/
├── public/                     # Static files served as-is (favicon, etc.)
├── src/
│   ├── app/                    # App shell: root component, providers, route table
│   │   ├── app.tsx
│   │   ├── providers.tsx       # QueryClientProvider, theme sync, devtools
│   │   └── router.tsx          # All routes (createBrowserRouter)
│   ├── components/
│   │   ├── ui/                 # shadcn/ui components (generated; edit sparingly)
│   │   └── layout/             # App layout (header, nav, <Outlet />)
│   ├── config/
│   │   └── env.ts              # Typed access to environment variables
│   ├── features/               # Feature modules, one folder per domain
│   │   └── posts/              # Example feature
│   │       ├── api/            # Axios calls (plain async functions)
│   │       ├── components/     # Feature-specific components
│   │       ├── hooks/          # TanStack Query hooks + query keys
│   │       ├── types.ts
│   │       └── index.ts        # Public exports of the feature
│   ├── hooks/                  # Shared, feature-agnostic hooks
│   ├── lib/                    # Shared setup: axios client, query client, cn()
│   ├── pages/                  # Route-level components (thin; compose features)
│   ├── stores/                 # Zustand stores (client/UI state only)
│   ├── types/                  # Shared TypeScript types
│   ├── index.css               # Tailwind entry + shadcn theme variables
│   ├── main.tsx                # Entry point
│   └── vite-env.d.ts           # Types for import.meta.env
├── components.json             # shadcn/ui CLI config
├── vite.config.ts
└── tsconfig*.json
```

Import from `src` with the `@/` alias, e.g. `import { Button } from '@/components/ui/button'`.

## Common tasks

### Add a page

1. Create `src/pages/<name>-page.tsx`.
2. Add a route for it in `src/app/router.tsx`.
3. (Optional) Add a nav link in `src/components/layout/root-layout.tsx`.

### Add an API-backed feature

1. Create `src/features/<feature>/`.
2. Add Axios calls in `api/` using `apiClient` from `@/lib/api-client`.
3. Wrap them in `useQuery` / `useMutation` hooks in `hooks/`, with a query-key factory.
4. Export the public pieces from the feature's `index.ts`.

Use `src/features/posts` as the template.

### Add a shadcn/ui component

```bash
npx shadcn@latest add dialog
```

Components are copied into `src/components/ui/`. See the full list at <https://ui.shadcn.com/docs/components>.

## Deployment

`npm run build` outputs static files to `dist/`, which you can host on any static host (S3 + CloudFront, Netlify, Vercel, Amplify, etc.).

Because this is an SPA with client-side routing, set up the host to **serve `index.html` for unknown paths**. Otherwise, refreshing on a URL like `/posts/1` returns 404. On S3 + CloudFront, map 403/404 errors to `/index.html` with status 200.
