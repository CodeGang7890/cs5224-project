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
| Workflow diagram | [React Flow](https://reactflow.dev) (`@xyflow/react`) |
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
| Orders | `/orders` |
| Service | `/service` |
| Payment | `/payment` |
| FAQ | `/faq` |
| Chats | `/chats` |
| Chat Sandbox | `/chat-sandbox` |

Home shows a random number fetched from `configuration-service` (see [Connecting to configuration-service](#connecting-to-configuration-service)). **Product** and **FAQ** let you add, edit and delete your business's products and FAQs (see [Managing products and FAQs](#managing-products-and-faqs)). **Workflow** shows your chat assistant's flow and lets you choose the customer details it collects (see [Editing the chat workflow](#editing-the-chat-workflow)). **Service** manages the services customers can book a time for and your team's weekly availability (see [Services and availability](#services-and-availability)). **Orders** lists the orders and bookings customers confirmed in chats, read only (see [Orders](#orders)). **Chats** lists your business's conversations, read only (see [Chats](#chats)). **Chat Sandbox** lets you chat with your assistant as a pretend customer (see [Chat Sandbox](#chat-sandbox)). The other pages are placeholders for now. Workflow, Product, Service, Orders, FAQ, Chats and Chat Sandbox require login: when you're logged out, they show "You need to be logged in to access this page" with a Log In button (see [Login-protected pages](#login-protected-pages)).

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

The **Workflow** tab (login required) shows how your chat assistant handles each customer message, and edits your business's chat configuration on `configuration-service` (`GET` / `PUT /api/chat/configuration/`). The flow is the same for every business; you configure its steps.

- **The diagram** (read only): every message goes to the **Router**, which decides what it's about and sends it down one or more branches: **Orders** (Product selection → Details collection → Confirmation), **Questions** (FAQs), and **Past orders** (Order status, *Coming soon*). Pan by dragging the background, and zoom with the mouse wheel or the controls in the corner.
- **Click a block** to see what it does. Product selection uses your active products and their stock, FAQs uses your FAQs, and Confirmation places orders, so their dialogs link to the Product, FAQ and Orders tabs. Order status isn't available yet: the assistant tells customers it's coming soon.
- **Choose the details to collect:** click the **Details collection** block (it lists the details it asks for). In the dialog:
  - **Basic details:** Name and Email are on by default; Phone number and Delivery address can be switched on. Switch any of them off, or rename them (e.g. "Receiver name").
  - **Custom details:** **Add a detail** with a label, a type (Text, Number, Email address or Phone number), limits (max characters for text; minimum / maximum for numbers) and an optional hint for the assistant (e.g. "6 digits"). Use Text for codes with leading zeros, like postal code `018956`.
  - **Required:** every detail has a **Required** switch (on by default). The chat only moves on once every required detail is given and valid, and the assistant keeps asking for them. Optional details are asked for once and can be skipped. At least one detail must be required. Optional ones show "(optional)" on the block.
  - **Apply** updates the block, then **Save changes** saves it. The assistant asks for each detail by its label exactly as you wrote it, so pick labels customers will understand.
- **Save / Discard** appear once you change something, and both ask for confirmation. **Save** sends the details (`PUT`). **Discard** re-fetches the saved configuration from the server. The backend validates every save; its errors appear in the save dialog. Until you save, your business uses the default details (Name and Email).
- Leaving the tab, or closing or reloading the page, with unsaved changes asks you to confirm first.
- Accounts without a business (e.g. `superuser`) see a message instead of the diagram.

## Services and availability

The **Service** tab (login required) is for businesses that sell time slots, like a photographer's shoots. It has two sections, on `configuration-service`'s `/api/services/` and `/api/weekly-availabilities/`.

- **Services:** add, edit and delete what customers can book: name, description, information (for the chat assistant), price, duration and buffer (time blocked after each booking without the customer, e.g. to tidy up; both in multiples of 15 minutes), active, and **who can do it**: a checkbox per weekly availability. A service with no one ticked can't be booked.
- **Weekly availability:** one calendar per person (e.g. each photographer), shown as a card with its hours and services. **Edit** opens the calendar:
  - **Weekly hours:** a week of 15-minute blocks. Pick a brush (**Available** O, **Taken** X, **On hold** H) and click or drag over the blocks; or tick some days, pick a time range and **Set**; or use a preset (weekdays 9am–6pm, every day 10am–8pm, clear all). Only available blocks can be booked. The times are your business's local time.
  - **Bookings by week** (saved calendars): any week of the calendar, with its bookings drawn over the weekly hours: on hold while pending payment, taken once paid, including each booking's buffer.
- Every save and delete asks for confirmation. Deleting a service or a calendar keeps its bookings.

## Orders

The **Orders** tab (login required) has two read-only sub-tabs: **Products** (orders) and **Services** (bookings, `?tab=services`). **Products** lists your business's orders from `GET /api/orders/`. An order is created when a customer replies CONFIRM at the chat's Confirmation step (in a real chat or a Chat Sandbox chat); it starts as *Pending payment*, and its products' stock is reserved (`quantity_available` → `quantity_on_hold`, visible on the Product tab).

- **Columns:** order number (with a *Sandbox* badge for test orders), customer (their name, else email), items, total, status (*Pending payment*, *Payment received*, *Completed*) and when it was placed.
- **Click a row** (or the eye icon) to see the order: each item with unit price, quantity and subtotal, the total, and the customer details collected in the chat (labelled as in your Details collection settings).
- **Filters:** status, and which orders (*Customer + sandbox*, the default, since sandbox orders hold real stock; *Customer orders*; *Sandbox only*). **Sort by** newest, oldest or status. **Pagination** with 10, 20, 50 or 100 per page.
- Everything is kept in the URL (e.g. `/orders?status=pending_payment&page=2`). The open order is `?order=<id>`, so the Chat Sandbox can link straight to an order; if it isn't on the current page, it's loaded on its own (another business's order or an unknown one shows a message).
- Orders can't be edited or deleted here yet; statuses will change once payment is set up.

## Chats

The **Chats** tab (login required) is a **read-only** list of your business's chats from `GET /api/chat/sessions/`. There's no editing or deleting here.

- **Columns:** customer (name, phone number, a *Sandbox* badge for test chats), current step in the chat flow, number of messages, last message, last chat time and start date.
- **Click a row** (or the eye icon) to read the whole conversation in a dialog, with what the chat flow has collected (order and total, each customer detail, the last order placed). Business messages are on the right, labelled *Assistant* (automated) or *Business* (typed by a person).
- **Search** by name or phone number (as you type).
- **Filters:** which chats (*Customer chats*, the default; *Customer + sandbox*; *Sandbox only*), current step (Start, Product selection, Details collection or Confirmation), with or without messages, last-chat date range and start date range. **Clear filters** resets them.
- **Sort by** most recent or oldest chat, newest or oldest started, name (A–Z / Z–A) or phone number.
- **Pagination:** previous / next, "Page X of Y", and 10, 20, 50 or 100 per page.
- Everything is kept in the URL (e.g. `/chats?sandbox=include&ordering=display_name&page=2`), so you can refresh, share a link or use the back button. The open conversation is `?chat=<id>`.

## Chat Sandbox

The **Chat Sandbox** tab (login required) lets you test your chat assistant by pretending to be a customer, in as many separate test chats as you like. Test chats are **sandbox chat sessions** on `configuration-service` (`is_sandbox = true`), kept apart from real customer chats.

- **The left panel lists your sandbox chats**, most recent first, with the last message. `GET /api/chat/sandbox-sessions/` (20 at a time; **Load more** fetches the next page).
- **New chat** creates one: `POST /api/chat/sandbox-sessions/`, named "Test chat N". It starts with no order in progress.
- **Click a chat to open it.** The open chat is kept in the URL (`?session=<id>`), so a refresh keeps it open. Each chat keeps its own unsent text.
- **Send a message:** `POST /api/chat/sandbox-sessions/{id}/messages/`. The backend saves it, runs the chat flow (the router decides what your message is about, and the order steps move the chat on; see "Chat flow" in `../configuration-service/README.md`), and saves and returns the LLM's reply. Your message appears straight away with a typing indicator. You can switch to another chat while waiting: the list shows "Waiting for reply…" and the reply lands in the right chat.
- **Confirming an order:** once your details are in, the assistant sends a fixed summary and asks you to reply CONFIRM (anything else just sends the summary again). Confirming saves the order first, then the assistant says it's confirmed, with its number; the chat goes back to the start, so you can order again, and the strip shows *Order #N placed*, which links to it in the Orders tab. If a product sold out in the meantime, the assistant says so, no order is placed, and you're back at choosing products.
- **The strip under the chat's header** shows where the chat is (*Step*: Start, Product selection, Details collection, Confirmation) and what it has collected: the order with its total, each customer detail collected (labelled as in your Details collection settings), and *Order #N placed* once an order is placed. It updates after each reply. To try the whole flow: ask to order, pick products and quantities, say that's everything when the assistant recaps your order and asks if you want anything else, give the details your Details collection step asks for, then reply CONFIRM to the summary. To try the other branches, ask a question about your business, or ask about a past order (the assistant says that's coming soon).
- **Debug panel:** the bug icon in the chat's header opens a panel beside the chat (kept in the URL as `?debug`). **Saved state** shows the raw `chat_state_id`, its step and the `chat_state_data` JSON. **Latest turn** shows what happened inside the last message you sent: the state before → after, the router's intents (and its prompt and JSON), each order step's extraction (what the LLM returned, whether the check passed or went back, what's missing, problems, and the prompt sent), why it stopped, the Confirmation substage (not confirmed / confirmed) and the order placed, whether the reply was written by the LLM or is a fixed template, the question check (if the router found a question), the reply prompt and any tool calls. The latest turn comes from the send response and isn't stored, so it's empty after a reload until you send another message.
- **Delete a chat** with the bin icon in its header, after a confirmation: `DELETE /api/chat/sandbox-sessions/{id}/`.
- Enter sends, Shift+Enter adds a new line. Messages can be up to 4,096 characters. Replies can take a while (the backend may ask the LLM several times per message), so sending waits up to 5 minutes instead of the usual 15 seconds.
- If the LLM fails, you see an error, but your message is still saved in the chat.
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
│   │   ├── services/           # Services + weekly availability calendars (Service tab)
│   │   ├── workflow/           # Chat flow diagram + Details collection settings (Workflow tab, React Flow)
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
