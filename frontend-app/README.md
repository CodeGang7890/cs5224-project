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

### Or with Docker

From the repository root, `docker compose up --build` starts the frontend together with PostgreSQL and
configuration-service, at <http://localhost:5173>. It runs the same dev server (`Dockerfile.dev`) with
the source mounted, so hot reload works; file watching uses polling (`CHOKIDAR_USEPOLLING`, see
`vite.config.ts`) because file events don't reach the container on WSL/Windows. After changing
`package.json`, run `docker compose up --build -V frontend-app` to reinstall the dependencies.

## Scripts

| Command | What it does |
| --- | --- |
| `npm run dev` | Starts the dev server with hot module reload |
| `npm run build` | Type-checks (`tsc -b`) and builds for production into `dist/` |
| `npm run preview` | Serves the production build locally so you can check it |
| `npm run lint` | Lints the code with oxlint |
| `npm run format` | Formats the code with Prettier (its default style; `npm run format:check` only checks) |

## Pages

| Tab | Sub-tabs (URL) |
| --- | --- |
| Home | `/` |
| Workflow | `/workflow` |
| Catalog | Products `/catalog/products`, Services `/catalog/services`, FAQs `/catalog/faqs` |
| Orders | Products `/orders/products`, Services `/orders/services`, Payment `/orders/payment` |
| Chats | Conversations `/chats/conversations`, Unanswered questions `/chats/questions`, Chat Sandbox `/chats/sandbox` |

Home shows the **WhatsApp** card (connect your business's WhatsApp number, see [Connecting WhatsApp](#connecting-whatsapp)) and a random number fetched from `configuration-service` (see [Connecting to configuration-service](#connecting-to-configuration-service)). **Workflow** shows your chat assistant's flow and lets you choose the customer details it collects (see [Editing the chat workflow](#editing-the-chat-workflow)). **Catalog** is what you sell and answer questions about: products and FAQs to add, edit and delete (see [Managing products and FAQs](#managing-products-and-faqs)), and the services customers can book a time for, with your service providers and their schedules (see [Services and availability](#services-and-availability)). **Orders** lists the orders and bookings customers confirmed in chats, read only (see [Orders](#orders)); Payment is a placeholder for now. **Chats** has your business's conversations, read only (see [Chats](#chats)), the questions the assistant couldn't answer, and the Chat Sandbox, to chat with your assistant as a pretend customer (see [Chat Sandbox](#chat-sandbox)). Opening `/catalog`, `/orders` or `/chats` shows its first sub-tab.

Everything except Home requires login. While you're logged out, only the Home tab is shown; if you open another page's URL, it shows "You need to be logged in to access this page" with a Log In button (see [Login-protected pages](#login-protected-pages)). Old URLs (`/product`, `/service`, `/faq`, `/payment`, `/chat-sandbox`, `/orders?tab=services`, `/chats?tab=questions`) redirect to their new place.

The top right shows **Log In** when you're logged out. When you're logged in, it shows your username, a profile icon and **Log Out** (see [Authentication](#authentication)). The profile modal's open state is kept in the URL as `?profile`, so you can link to it directly and the browser's back button closes it.

## Connecting WhatsApp

The **WhatsApp** card on Home (login required; your account must belong to a business) connects your business's WhatsApp Business number with **Connect with Facebook** (Meta's WhatsApp Embedded Signup), so customers' messages reach your assistant.

1. Click **Connect with Facebook**, then **Continue to Facebook**.
2. In Facebook's window: log in, choose or create your WhatsApp Business account, and add and verify your business phone number.
3. When you finish, the card shows *Connecting…*, then the number Meta verified (e.g. "+65 9123 4567 · Kopi & Co. Café"). The webhook is set up automatically: there's nothing to enter in Meta.

Once connected, **Reconnect with Facebook** replaces the connection and **Disconnect** removes it (both ask for confirmation). The button needs `VITE_META_APP_ID` and `VITE_META_CONFIG_ID`; until they're set it does nothing. Meta only allows the Facebook window on HTTPS domains set on our app, so it can't be completed on localhost.

## Connecting to configuration-service

The Home tab calls `GET /api/configuration/random-number/` on the Django backend in `../configuration-service`. To see it working:

1. Start the backend (see `../configuration-service/README.md`): `python manage.py runserver`. It serves on <http://127.0.0.1:8000>.
2. Start the frontend: `npm run dev`. It serves on <http://localhost:5173>.
3. Open <http://localhost:5173>. The Home tab shows a number from 1 to 10; the refresh button fetches a new one.

If the backend isn't running, the card shows an error message instead. The backend's CORS settings allow `http://localhost:5173` by default.

## Managing products and FAQs

When you're logged in, **Catalog → Products** and **Catalog → FAQs** list your business's records. Each has an **Add** button, and each record has **Edit** (pencil) and **Delete** (bin) buttons.

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

- **The diagram** (read only): every message goes to the **Router**, which decides what it's about and sends it down one or more branches: **Orders** (Product selection → Details collection → Confirmation), **Bookings** (Service selection → Time slot → Booking details → Booking confirmation, for the services in Catalog → Services), **Questions** (FAQs), and **Past orders** (Order status: the customer's own orders and bookings, and their status). Details collection (orders) and Booking details (bookings) each ask for their own details. Pan by dragging the background, and zoom with the mouse wheel or the controls in the corner.
- **Click a block** to see what it does. Product selection uses your active products and their stock, FAQs uses your FAQs, and Confirmation places orders, so their dialogs link to the Product, FAQ and Orders tabs. Order status looks up the customer's own past orders and bookings (same phone number) in code, and the reply may only repeat what was found, with each one's status; its dialog links to the Orders tab.
- **Welcome message and style:** click the **Welcome & style** block (left of the Router). Switch on a welcome message (up to 1,000 characters; `{business_name}` is replaced by your business's name, with a preview), sent as the reply to a customer's first message: alone if they only said hello, or before the assistant's reply. Pick how the assistant writes: Friendly (the default), Professional, Casual, Brief, or Custom (describe it yourself, up to 500 characters). The style only changes the tone; fixed messages like order summaries stay the same. **Apply**, then **Save changes**.
- **Choose the details to collect:** click the **Details collection** block for product orders, or the **Booking details** block for service bookings: each has its own list (each block lists the details it asks for). In the dialog:
  - **Basic details:** Name and Email are on (and required) by default; Delivery address can be switched on. There's no phone number: customers chat on WhatsApp, so you already have it. Switch any of them off, or rename them (e.g. "Receiver name").
  - **Custom details:** **Add a detail** with a label, a type (Text, Number or Email address), limits (max characters for text; minimum / maximum for numbers) and an optional hint for the assistant (e.g. "6 digits"). Use Text for codes with leading zeros, like postal code `018956`.
  - **Required:** every detail has a **Required** switch (on by default). The chat only moves on once every required detail is given and valid, and the assistant keeps asking for them. Optional details are asked for once and can be skipped. At least one detail must be required. Optional ones show "(optional)" on the block.
  - **Apply** updates the block, then **Save changes** saves it. The assistant asks for each detail by its label exactly as you wrote it, so pick labels customers will understand.
- **Save / Discard** appear once you change something, and both ask for confirmation. **Save** sends the details (`PUT`). **Discard** re-fetches the saved configuration from the server. The backend validates every save; its errors appear in the save dialog. Until you save, your business uses the default details (Name and Email).
- Leaving the tab, or closing or reloading the page, with unsaved changes asks you to confirm first.
- Accounts without a business (e.g. `superuser`) see a message instead of the diagram.

## Services and availability

**Catalog → Services** (login required) is for businesses that sell time slots, like a photographer's shoots. It uses `configuration-service`'s `/api/services/`, `/api/service-providers/` and `/api/weekly-availabilities/`.

- **Services:** add, edit and delete what customers can book: name, description, information (for the chat assistant), price, duration and buffer (time blocked after each booking without the customer, e.g. to tidy up; both in multiples of 15 minutes), **bookings start every** 15 min, 30 min, 1 hour or a custom number of minutes (counted from midnight: with 30 min, a booking can start at 9:00 or 9:30 but not 9:15), active, and **who can do it**: a checkbox per service provider. A service with no one ticked can't be booked.
- **Service providers:** each person (or room) services are booked with, e.g. each photographer, as a card with their services. Add, edit (name, note, active) and delete them; **View schedule** opens their schedule below.
- **Schedules:** pick a provider and a week (previous / this week / next, or a date; `?provider=` and `?week=` in the URL). The week is shown in 15-minute blocks: **Available** (O), **Unavailable** (U), **On hold** (H: booked, waiting for payment) and **Booked** (X: paid). Bookings set H and X themselves, so these blocks can't be edited. The times are your business's local time.
  - **Click a booking** to see who booked it, their details, the status (pending payment / paid / completed), and links to the booking in the Orders tab and its chat.
  - **Edit hours:** click or drag over the blocks to make them available or unavailable, then **Save week**.
  - **Add slots:** open (or close) the same times on some days over a range of dates, e.g. the next 2 weeks, Monday to Friday, 9am to 5pm.
  - **Copy previous week** into this one, or **Copy to next weeks** (1 to 26 weeks). Booked times are never changed.
- Every save and delete asks for confirmation. Deleting a service or a provider keeps its bookings.

## Orders

The **Orders** tab (login required) has two sub-tabs: **Products** (orders, `/orders/products`) and **Services** (bookings, `/orders/services`), plus **Payment** (a placeholder). They're read only, except that a paid order or booking (*Payment received*) has a **Mark as completed** button in its dialog, which asks you to confirm and then sets it to *Completed* (for an order, its products count as sold). Statuses: *Pending payment*, *Payment received*, *Completed* and *Payment failed* (a failed payment holds no stock or time; pending → received / failed will be set by the payment service later). **Products** lists your business's orders from `GET /api/orders/`. An order is created when a customer replies CONFIRM at the chat's Confirmation step (in a real chat or a Chat Sandbox chat); it starts as *Pending payment*, and its products' stock is reserved (`quantity_available` → `quantity_on_hold`, visible on the Product tab).

- **Columns:** order number (with a *Sandbox* badge for test orders), customer (their name, else email), items, total, status (*Pending payment*, *Payment received*, *Completed*) and when it was placed.
- **Click a row** (or the eye icon) to see the order: each item with unit price, quantity and subtotal, the total, and the customer details collected in the chat (labelled as in your Details collection settings).
- **Filters:** status, and which orders (*Customer + sandbox*, the default, since sandbox orders hold real stock; *Customer orders*; *Sandbox only*). **Sort by** newest, oldest or status. **Pagination** with 10, 20, 50 or 100 per page.
- Everything is kept in the URL (e.g. `/orders/products?status=pending_payment&page=2`). The open order is `?order=<id>`, so the Chat Sandbox can link straight to an order; if it isn't on the current page, it's loaded on its own (another business's order or an unknown one shows a message).
- Orders can't be edited or deleted here yet; statuses will change once payment is set up.

## Chats

**Chats → Conversations** (login required) is a **read-only** list of your business's chats from `GET /api/chat/sessions/`. There's no editing or deleting here.

- **Columns:** customer (name, phone number, a *Sandbox* badge for test chats), current step in the chat flow, number of messages, last message, last chat time and start date.
- **Click a row** (or the eye icon) to read the whole conversation in a dialog, with what the chat flow has collected (order and total, each customer detail, the last order placed). Business messages are on the right, labelled *Assistant* (automated) or *Business* (typed by a person).
- **Search** by name or phone number (as you type).
- **Filters:** which chats (*Customer chats*, the default; *Customer + sandbox*; *Sandbox only*), current step (Start, Product selection, Details collection or Confirmation), with or without messages, last-chat date range and start date range. **Clear filters** resets them.
- **Sort by** most recent or oldest chat, newest or oldest started, name (A–Z / Z–A) or phone number.
- **Pagination:** previous / next, "Page X of Y", and 10, 20, 50 or 100 per page.
- Everything is kept in the URL (e.g. `/chats/conversations?sandbox=include&ordering=display_name&page=2`), so you can refresh, share a link or use the back button. The open conversation is `?chat=<id>`.

## Chat Sandbox

**Chats → Chat Sandbox** (login required) lets you test your chat assistant by pretending to be a customer, in as many separate test chats as you like. Test chats are **sandbox chat sessions** on `configuration-service` (`is_sandbox = true`), kept apart from real customer chats.

- **The left panel lists your sandbox chats**, most recent first, with the last message. `GET /api/chat/sandbox-sessions/` (20 at a time; **Load more** fetches the next page).
- **New chat** creates one: `POST /api/chat/sandbox-sessions/`, named "Test chat N". It starts with no order in progress.
- **Click a chat to open it.** The open chat is kept in the URL (`?session=<id>`), so a refresh keeps it open. Each chat keeps its own unsent text.
- **Send a message:** `POST /api/chat/sandbox-sessions/{id}/messages/`. The backend saves it, runs the chat flow (the router decides what your message is about, and the order steps move the chat on; see "Chat flow" in `../configuration-service/README.md`), and saves and returns the LLM's reply. Your message appears straight away with a typing indicator. You can switch to another chat while waiting: the list shows "Waiting for reply…" and the reply lands in the right chat.
- **Confirming an order:** once your details are in, the assistant sends a fixed summary and asks you to reply CONFIRM (anything else just sends the summary again). Confirming saves the order first, then the assistant says it's confirmed, with its number; the chat goes back to the start, so you can order again, and the strip shows *Order #N placed*, which links to it in the Orders tab. If a product sold out in the meantime, the assistant says so, no order is placed, and you're back at choosing products.
- **The strip under the chat's header** shows where the chat is (*Step*: Start, Product selection, Details collection, Confirmation) and what it has collected: the order with its total, each customer detail collected (labelled as in your Details collection settings), and *Order #N placed* once an order is placed. It updates after each reply. To try the whole flow: ask to order, pick products and quantities, say that's everything when the assistant recaps your order and asks if you want anything else, give the details your Details collection step asks for, then reply CONFIRM to the summary. To try the other branches, ask a question about your business, or ask about a past order (the assistant tells you the status of this test customer's orders; the debug panel shows what was looked up). With services set up (Catalog → Services), ask to book one: the assistant offers numbered free times; reply with a number (or ask for another day or time), give your details, then CONFIRM; the booking appears in the Orders tab under Services, and the strip shows *Booking #N made*.
- **Debug panel:** the bug icon in the chat's header opens a panel beside the chat (kept in the URL as `?debug`). **Saved state** shows the raw `chat_state_id`, its step and the `chat_state_data` JSON. **Latest turn** shows what happened inside the last message you sent: the state before → after, the router's intents (and its prompt and JSON), each order step's extraction (what the LLM returned, whether the check passed or went back, what's missing, problems, and the prompt sent), why it stopped, the Confirmation substage (not confirmed / confirmed) and the order placed, whether the reply was written by the LLM or is a fixed template, the question check (if the router found a question), the reply prompt and any tool calls. The latest turn comes from the send response and isn't stored, so it's empty after a reload until you send another message.
- **Delete a chat** with the bin icon in its header, after a confirmation: `DELETE /api/chat/sandbox-sessions/{id}/`.
- Enter sends, Shift+Enter adds a new line. Messages can be up to 4,096 characters. Replies can take a while (the backend may ask the LLM several times per message), so sending waits up to 5 minutes instead of the usual 15 seconds.
- If the LLM fails, you see an error, but your message is still saved in the chat.
- You need `configuration-service` and Ollama running (see `../configuration-service/README.md`).

## Authentication

Users log in with their `configuration-service` username and password (e.g. `kopi_owner` / `123` from the sample data), or with **Google or Facebook**, and new users can **sign up**. Either way, the backend issues **JWTs** through SimpleJWT:
- **Access token:** valid for 15 minutes, sent as `Authorization: Bearer <token>`.
- **Refresh token:** valid for 7 days. It's used to get new access tokens.

How it works in the app:
- **Log In** and **Sign Up** open the same dialog: *Continue with Google / Facebook*, or a username and password (`POST /api/auth/token/`), or the sign-up form (`POST /api/auth/signup/`: name, username, email, password). After logging in, the app loads your profile from `GET /api/auth/me/`, including your business ID, and shows your username in the header.
- **Google / Facebook** go through Google Cloud Identity Platform (the Firebase JS SDK, `src/lib/firebase.ts`): the popup's ID token is exchanged for our JWTs (`POST /api/auth/firebase/`). The first time creates your account. It needs `VITE_FIREBASE_API_KEY`, `VITE_FIREBASE_AUTH_DOMAIN` and `VITE_FIREBASE_PROJECT_ID` (`.env.example`); until they're set, the buttons do nothing.
- **A new account sets up its business first:** until it has one, every login-only page (and Home) shows **Set up your business** (name, location, description; `PUT /api/configuration/business/`), then the page appears.
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
| `VITE_MESSAGING_SERVICE_URL` | API root of `messaging-service`, used by `messagingApiClient`: the chat flow (the Chat Sandbox's messages, `/chat/sandbox-sessions/{id}/messages/`). | `http://localhost:8004/api` |

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
│   │   ├── navigation.ts       # Route paths, top-nav tabs, sections' sub-tabs
│   │   └── env.ts              # Typed access to environment variables
│   ├── features/               # Feature modules, one folder per domain
│   │   ├── auth/               # Login / sign-up dialog (+ Google / Facebook), RequireAuth guard, useAuth / useCurrentUser hooks, auth API calls
│   │   ├── business/           # Your business: "Set up your business" after sign up, RequireBusiness guard
│   │   ├── products/           # Product list + add/edit/delete dialogs (Catalog → Products)
│   │   ├── faqs/               # FAQ list + add/edit/delete dialogs (Catalog → FAQs)
│   │   ├── services/           # Services, service providers and their schedules (Catalog → Services)
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
4. To show it as a top-nav tab, add it to `navItems` in `src/config/navigation.ts` (`requiresAuth: true` hides it while logged out). For a sub-tab of Catalog / Orders / Chats, add it to that section's tabs there (`catalogTabs`, …), route it as a child of the section's route, and wrap the page in `TabPage`.

### Add an API-backed feature

1. Create `src/features/<feature>/`.
2. Add Axios calls in `api/` using the service's client from `@/lib/api-client` (e.g. `configurationApiClient`). Authentication is handled by the client, so don't add auth headers yourself. For a new backend service, add a client with `createApiClient(env.<serviceUrl>)`.
3. Wrap them in `useQuery` / `useMutation` hooks in `hooks/`, with a query-key factory.
4. Export the public pieces from the feature's `index.ts`.

Use `src/features/random-number` as the template for read-only data, and `src/features/products` for full CRUD with forms and confirmations.

### Keep `package-lock.json` on the public registry

CI installs from `https://registry.npmjs.org/`, so every `"resolved"` URL in `package-lock.json` must point there. If your npm uses a private mirror (e.g. `npm.apple.com`), `npm install` writes the mirror's URLs, and CI fails. Point them back with:

```bash
sed -i '' -E 's#"resolved": "https://artifacts\.apple\.com/artifactory/api/npm/npm-apple/#"resolved": "https://registry.npmjs.org/#; s#"resolved": "https://npm\.apple\.com/#"resolved": "https://registry.npmjs.org/#' package-lock.json
```

Installing still works behind the mirror: npm swaps `registry.npmjs.org` for your configured registry (`replace-registry-host`).

### Add a shadcn/ui component

```bash
npx shadcn@latest add tabs
```

Components are copied into `src/components/ui/`. See the full list at <https://ui.shadcn.com/docs/components>.

## Deployment

`npm run build` outputs static files to `dist/`, which you can host on any static host (S3 + CloudFront, Netlify, Vercel, Amplify, etc.).

Because this is an SPA with client-side routing, set up the host to **serve `index.html` for unknown paths**. Otherwise, refreshing on a URL like `/workflow` returns 404. On S3 + CloudFront, map 403/404 errors to `/index.html` with status 200.
