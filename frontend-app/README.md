# Ansera Business Admin (frontend-app)

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

## Pages

| Tab | URL |
| --- | --- |
| Home | `/` |
| Workflow | `/workflow` |
| Product | `/product` |
| Schedule | `/schedule` |
| Payment | `/payment` |
| FAQ | `/faq` |
| Chats | `/chats` |
| Chat Sandbox | `/chat-sandbox` |

Home shows a random number fetched from `configuration-service` (see [Connecting to configuration-service](#connecting-to-configuration-service)). The other pages are placeholders for now.

The top right shows **Log In** when you're logged out. When you're logged in, it shows your username, a profile icon and **Log Out** (see [Authentication](#authentication)). The profile modal's open state is kept in the URL as `?profile`, so you can link to it directly and the browser's back button closes it.

## Connecting to configuration-service

The Home tab calls `GET /api/configuration/random-number/` on the Django backend in `../configuration-service`. To see it working:

1. Start the backend (see `../configuration-service/README.md`): `python manage.py runserver`. It serves on <http://127.0.0.1:8000>.
2. Start the frontend: `npm run dev`. It serves on <http://localhost:5173>.
3. Open <http://localhost:5173>. The Home tab shows a number from 1 to 10; the refresh button fetches a new one.

If the backend isn't running, the card shows an error message instead. The backend's CORS settings allow `http://localhost:5173` by default.

## Authentication

Users log in with their `configuration-service` username and password, e.g. `kopi_owner` / `123` from the sample data. The backend issues **JWTs** through SimpleJWT:
- **Access token:** valid for 15 minutes, sent as `Authorization: Bearer <token>`.
- **Refresh token:** valid for 7 days. It's used to get new access tokens.

How it works in the app:
- **Log In** opens a username/password dialog (`POST /api/auth/token/`). After logging in, the app loads your profile from `GET /api/auth/me/`, including your business ID, and shows your username in the header.
- **You don't write any auth code per request.** Every Axios client made with `createApiClient` (in `src/lib/api-client.ts`):
  - attaches the access token automatically;
  - on a `401`, refreshes the tokens once and retries the request. Simultaneous requests share a single refresh.
  - If the refresh fails (7 days passed, or you logged out), you're logged out automatically.
- **Tokens persist across reloads.** They're kept in `localStorage` (the Zustand store in `src/stores/auth-store.ts`) and stay in sync across browser tabs.
- **Log Out** discards the tokens and asks the backend to revoke the refresh token (`POST /api/auth/logout/`).
- **Logging in or out clears all cached data,** so one user's data is never shown to another.

In components, use the `useAuth()` hook:

```tsx
import { useAuth } from '@/features/auth'

const { isAuthenticated, user, login, logout } = useAuth()
// user: { id, username, email, first_name, last_name, business, business_name, ... }
```

Calling a protected API needs nothing extra:

```ts
const { data } = await configurationApiClient.get('/products/') // token attached + refreshed automatically
```

## Environment variables

Vite only exposes variables that start with `VITE_`. Put local values in `.env.local`, which git ignores.

| Variable | Description | Default |
| --- | --- | --- |
| `VITE_CONFIGURATION_SERVICE_URL` | API root of `configuration-service`, used by `configurationApiClient`. Request paths are relative to it, e.g. `/auth/me/`, `/products/`, `/configuration/random-number/`. | `http://localhost:8000/api` |

> [!NOTE]
> This variable changed from `…/api/configuration` to `…/api` when authentication was added. If you have a `.env.local`, update it.

When you add a variable, add it to `.env.example`, `src/vite-env.d.ts` (types) and `src/config/env.ts`.

## Project structure

```
frontend-app/
├── public/                     # Static files served as-is (favicon, etc.)
├── src/
│   ├── app/                    # App shell: root component, providers, route table
│   │   ├── app.tsx
│   │   ├── providers.tsx       # QueryClientProvider, theme sync, devtools
│   │   ├── routes.tsx          # Route table (RouteObject[])
│   │   └── router.tsx          # createBrowserRouter(routes)
│   ├── components/
│   │   ├── ui/                 # shadcn/ui components (generated; edit sparingly)
│   │   ├── common/             # Shared app components (e.g. PagePlaceholder)
│   │   └── layout/             # App layout: header (nav tabs, AuthControls), <Outlet />
│   ├── config/
│   │   ├── app.ts              # App name
│   │   ├── navigation.ts       # Route paths + top-nav tabs
│   │   └── env.ts              # Typed access to environment variables
│   ├── features/               # Feature modules, one folder per domain
│   │   ├── auth/               # Login dialog, useAuth / useCurrentUser hooks, auth API calls
│   │   ├── profile/            # Profile modal (data from /api/auth/me/)
│   │   └── random-number/      # Sample configuration-service call (shown on Home)
│   │       ├── api/            # Axios calls (plain async functions)
│   │       ├── components/     # Feature-specific components
│   │       ├── hooks/          # TanStack Query hooks + query keys
│   │       ├── types.ts
│   │       └── index.ts        # Public exports of the feature
│   ├── hooks/                  # Shared, feature-agnostic hooks
│   ├── lib/                    # Shared setup: axios client, query client, cn()
│   ├── pages/                  # Route-level components (thin; compose features)
│   ├── stores/                 # Zustand stores: theme, auth tokens (client state only)
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

1. Create `src/pages/<name>-page.tsx`. `PagePlaceholder` is a good starting point.
2. Add its path to `paths` in `src/config/navigation.ts`.
3. Add a route for it in `src/app/routes.tsx`.
4. To show it as a top-nav tab, add it to `navItems` in `src/config/navigation.ts`.

### Add an API-backed feature

1. Create `src/features/<feature>/`.
2. Add Axios calls in `api/` using the service's client from `@/lib/api-client` (e.g. `configurationApiClient`). Authentication is handled by the client, so don't add auth headers yourself. For a new backend service, add a client with `createApiClient(env.<serviceUrl>)`.
3. Wrap them in `useQuery` / `useMutation` hooks in `hooks/`, with a query-key factory.
4. Export the public pieces from the feature's `index.ts`.

Use `src/features/random-number` as the template.

### Add a shadcn/ui component

```bash
npx shadcn@latest add tabs
```

Components are copied into `src/components/ui/`. See the full list at <https://ui.shadcn.com/docs/components>.

## Deployment

`npm run build` outputs static files to `dist/`, which you can host on any static host (S3 + CloudFront, Netlify, Vercel, Amplify, etc.).

Because this is an SPA with client-side routing, set up the host to **serve `index.html` for unknown paths**. Otherwise, refreshing on a URL like `/workflow` returns 404. On S3 + CloudFront, map 403/404 errors to `/index.html` with status 200.
