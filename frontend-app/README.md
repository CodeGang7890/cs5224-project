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
| Workflow editor (drag and drop, arrows) | [React Flow](https://reactflow.dev) (`@xyflow/react`) |
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

Home shows a random number fetched from `configuration-service` (see [Connecting to configuration-service](#connecting-to-configuration-service)). **Product** and **FAQ** let you add, edit and delete your business's products and FAQs (see [Managing products and FAQs](#managing-products-and-faqs)). **Workflow** is a drag-and-drop editor for your business's chat flow (see [Editing the chat workflow](#editing-the-chat-workflow)). **Chat Sandbox** lets you chat with your assistant as a pretend customer (see [Chat Sandbox](#chat-sandbox)). The other pages are placeholders for now. Workflow, Product, FAQ and Chat Sandbox require login: when you're logged out, they show "You need to be logged in to access this page" with a Log In button (see [Login-protected pages](#login-protected-pages)).

The top right shows **Log In** when you're logged out. When you're logged in, it shows your username, a profile icon and **Log Out** (see [Authentication](#authentication)). The profile modal's open state is kept in the URL as `?profile`, so you can link to it directly and the browser's back button closes it.

## Connecting to configuration-service

The Home tab calls `GET /api/configuration/random-number/` on the Django backend in `../configuration-service`. To see it working:

1. Start the backend (see `../configuration-service/README.md`): `python manage.py runserver`. It serves on <http://127.0.0.1:8000>.
2. Start the frontend: `npm run dev`. It serves on <http://localhost:5173>.
3. Open <http://localhost:5173>. The Home tab shows a number from 1 to 10; the refresh button fetches a new one.

If the backend isn't running, the card shows an error message instead. The backend's CORS settings allow `http://localhost:5173` by default.

## Managing products and FAQs

When you're logged in, the **Product** and **FAQ** tabs list your business's records. Each tab has an **Add** button, and each record has **Edit** (pencil) and **Delete** (bin) buttons.

- **Every save and delete asks for confirmation.** On edits, the confirmation lists what changed. Cancel leaves everything unchanged.
- **Editable fields follow the API** (`configuration-service`):

  | | Editable | Shown but read-only | Never sent |
  | --- | --- | --- | --- |
  | Product | name, description, price, quantity available, quantity on hold, active | quantity sold (managed by the system) | `id`, `business` (always your business), `quantity_sold` |
  | FAQ | question, answer | none | `id`, `business` |

- **Edits send only the fields you changed** (`PATCH`). **Save** is disabled until something changes.
- **Limits are checked as you type,** with character counters and messages:
  - Names: 150 characters. FAQ questions: 300 characters.
  - Descriptions: 5,000 characters. FAQ answers: 10,000 characters.
  - Price: ≥ 0, up to 2 decimal places.
  - Quantities: whole numbers from 0 to 1,000,000.
- **The backend checks everything again.** Its errors, such as "This business already has a product with this name", appear in the form.
- **Lists are paginated,** 20 per page, and the page is kept in the URL (`?page=2`).
- **To hide a product without deleting it,** edit it and turn off **Active**.

## Editing the chat workflow

The **Workflow** tab (login required) edits your business's chat configuration on `configuration-service` (`GET` / `PUT /api/chat/configuration/`).

- **Opening the tab loads the saved workflow.** If your business hasn't saved one yet, you start with just the **Start** block.
- **Add blocks** by dragging **Product selection**, **Details collection** or **Confirmation** from the left panel onto the canvas, or by clicking their **+**. There is always exactly one Start block: it can't be added or deleted.
- **Connect blocks** by dragging from a block's right dot to another block. Each block leads to at most one next block, so a new arrow replaces the old one. To remove an arrow, click it and press the **×** (or Delete/Backspace).
- **Delete a block** with the **×** in its top-right corner (or select it and press Delete/Backspace). Its arrows go with it.
- **Move blocks** by dragging them. Pan by dragging the background, and zoom with the mouse wheel or the controls in the corner.
- **Save / Discard** appear once you change something, and both ask for confirmation. **Save** sends the whole workflow (`PUT`). **Discard** re-fetches the saved workflow from the server. The backend validates every save; its errors appear in the save dialog.
- The toolbar warns about blocks that can't be reached from Start. They can still be saved.
- Leaving the tab, or closing or reloading the page, with unsaved changes asks you to confirm first.
- Accounts without a business (e.g. `superuser`) see a message instead of the editor.

## Chat Sandbox

The **Chat Sandbox** tab (login required) lets you test your chat assistant by pretending to be a customer. It uses the same `configuration-service` APIs a real customer chat would:

1. It finds your business's sandbox chat session: `GET /api/chat/sessions/?phone_number=%2B10000000000`.
2. If there isn't one yet, it creates it: `POST /api/chat/sessions/` with phone number `+10000000000` and display name `sandbox_user`. (`000` isn't a valid phone number for the backend, so the mock number is `+1` followed by zeros.) The session starts at your workflow's Start block, so **your business needs a saved workflow first**; otherwise the tab links you to the Workflow tab.
3. Each message you send goes to `POST /api/chat/sessions/messages/`. The backend saves it, asks the LLM (local Ollama) for a reply, saves and returns the reply. Your message appears straight away with a typing indicator, and the conversation is re-fetched afterwards.

- Enter sends, Shift+Enter adds a new line. Messages can be up to 4,096 characters.
- Replies can take a while (the local model may need to load), so this request waits up to 150 seconds instead of the usual 15.
- If the LLM fails, you see an error, but your message is still saved in the conversation.
- The conversation is kept between visits. There's no way to clear it from the app yet.
- You need `configuration-service` and Ollama running (see `../configuration-service/README.md`).

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

### Login-protected pages

`<RequireAuth>` (from `@/features/auth`) is a reusable login guard:
- **Logged in:** it renders the page.
- **Logged out:** it shows a "You need to be logged in to access this page" card with a **Log In** button. After you log in, the page appears in place, with no redirect. If you log out while on the page, the message comes back.

**To protect a page, add its route to the `RequireAuth` group** in `src/app/routes.tsx`. The page component itself needs no changes:

```tsx
{
  element: <RequireAuth />,
  children: [
    { path: paths.product, element: <ProductPage /> },
    { path: paths.faq, element: <FaqPage /> },
    // { path: paths.payment, element: <PaymentPage /> },  ← add more here
  ],
},
```

It also works as a plain wrapper, e.g. to protect just part of a page:

```tsx
<RequireAuth>
  <SomethingPrivate />
</RequireAuth>
```

The guard is a UI convenience only. The backend enforces access on every API call (`401`/`403`), so hiding a page doesn't need to be secure on its own.

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
│   │   ├── common/             # Shared app components: ConfirmDialog, FormField, PaginationControls, PagePlaceholder
│   │   └── layout/             # App layout: header (nav tabs, AuthControls), <Outlet />
│   ├── config/
│   │   ├── app.ts              # App name
│   │   ├── navigation.ts       # Route paths + top-nav tabs
│   │   └── env.ts              # Typed access to environment variables
│   ├── features/               # Feature modules, one folder per domain
│   │   ├── auth/               # Login dialog, RequireAuth guard, useAuth / useCurrentUser hooks, auth API calls
│   │   ├── products/           # Product list + add/edit/delete dialogs (Product tab)
│   │   ├── faqs/               # FAQ list + add/edit/delete dialogs (FAQ tab)
│   │   ├── workflow/           # Chat workflow editor (Workflow tab, React Flow)
│   │   ├── chat-sessions/      # Chat session API calls + Chat Sandbox
│   │   ├── profile/            # Profile modal (data from /api/auth/me/)
│   │   └── random-number/      # Sample configuration-service call (shown on Home)
│   │       ├── api/            # Axios calls (plain async functions)
│   │       ├── components/     # Feature-specific components
│   │       ├── hooks/          # TanStack Query hooks + query keys
│   │       ├── types.ts
│   │       └── index.ts        # Public exports of the feature
│   ├── hooks/                  # Shared hooks (theme, ?page= URL param)
│   ├── lib/                    # Shared setup: axios client, query client, cn(), getFormErrors()
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
3. Add a route for it in `src/app/routes.tsx`. If it needs login, put it inside the `RequireAuth` group.
4. To show it as a top-nav tab, add it to `navItems` in `src/config/navigation.ts`.

### Add an API-backed feature

1. Create `src/features/<feature>/`.
2. Add Axios calls in `api/` using the service's client from `@/lib/api-client` (e.g. `configurationApiClient`). Authentication is handled by the client, so don't add auth headers yourself. For a new backend service, add a client with `createApiClient(env.<serviceUrl>)`.
3. Wrap them in `useQuery` / `useMutation` hooks in `hooks/`, with a query-key factory.
4. Export the public pieces from the feature's `index.ts`.

Use `src/features/random-number` as the template for read-only data, and `src/features/products` for full CRUD with forms and confirmations.

### Add a shadcn/ui component

```bash
npx shadcn@latest add tabs
```

Components are copied into `src/components/ui/`. See the full list at <https://ui.shadcn.com/docs/components>.

## Deployment

`npm run build` outputs static files to `dist/`, which you can host on any static host (S3 + CloudFront, Netlify, Vercel, Amplify, etc.).

Because this is an SPA with client-side routing, set up the host to **serve `index.html` for unknown paths**. Otherwise, refreshing on a URL like `/workflow` returns 404. On S3 + CloudFront, map 403/404 errors to `/index.html` with status 200.
