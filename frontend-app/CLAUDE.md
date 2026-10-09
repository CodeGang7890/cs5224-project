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
| Workflow editor | **React Flow** (`@xyflow/react` v12) | Node/edge canvas for `features/workflow`. Import its CSS once (`@xyflow/react/dist/style.css`, done in `workflow-editor.tsx`). Pass `colorMode` from the theme store. Keep `nodeTypes`/`edgeTypes` objects at module level. |
| Lint | **oxlint** | `npm run lint`. Config in `.oxlintrc.json`. |

## Project structure conventions

- `src/app/`: app shell. `routes.tsx` is the route table (plain `RouteObject[]`, importable without a browser); `router.tsx` wraps it in `createBrowserRouter`; `providers.tsx` holds global providers.
- `src/config/`: `app.ts` (`APP_NAME`), `navigation.ts` (`paths` + top-nav `navItems`; use `paths` instead of hard-coded URLs), `env.ts` (typed env access).
- **Adding a page**: create `src/pages/<name>-page.tsx`, add its path to `paths`, add a route in `routes.tsx`, and add it to `navItems` if it's a top-nav tab. Pages set the browser tab title by rendering `<title>{`${title} | ${APP_NAME}`}</title>` (React 19 hoists it into `<head>`); `PagePlaceholder` does this already.
- `src/pages/`: route-level components. Keep them thin; they compose features. Current tabs (Home shows the WhatsApp card (`features/whatsapp`) and the random-number card; **Workflow, Product, Orders, FAQ, Chats and Chat Sandbox are behind `RequireAuth`**; Chats is a read-only chat list; Product and FAQ are CRUD pages, Workflow is the chat flow editor, Chat Sandbox runs test chats with the assistant as a pretend customer (sandbox sessions); the rest use `PagePlaceholder`): Home `/`, Workflow `/workflow`, Product `/product`, Orders `/orders`, Schedule `/schedule`, Payment `/payment`, FAQ `/faq`, Chats `/chats`, Chat Sandbox `/chat-sandbox`. 
- `src/features/<feature>/`: self-contained domain modules with `api/` (Axios functions), `hooks/` (TanStack Query hooks + keys), `components/`, `types.ts`, and an `index.ts` public API. Import features via `@/features/<feature>`, not their internal paths. `features/random-number` is the reference example for the Axios + TanStack Query pattern: it calls `GET /api/configuration/random-number/` on configuration-service and is shown on the Home page. `features/auth` holds the login dialog, auth API calls and the `useAuth` / `useCurrentUser` hooks. `features/products` and `features/faqs` implement CRUD (see "CRUD pattern" below). `features/chat-sessions` holds the chat session API calls and the Chat Sandbox (see "Chat Sandbox" below). `features/workflow` is the chat configuration editor (see "Workflow editor" below). `features/orders` is the read-only Orders tab (see "Orders tab" below). `features/profile` holds the profile modal (`ProfileDialog`), which shows `useCurrentUser()` data. `features/whatsapp` is the WhatsApp connection card (see "WhatsApp card" below).
- `src/components/ui/`: shadcn-generated code. Prefer composing or wrapping over heavy edits. The oxlint `only-export-components` rule is disabled for this folder.
- `src/components/layout/`: layout components. `RootLayout` renders the sticky header (app name, nav tabs, theme toggle, `AuthControls`) and the `<Outlet />`. `AuthControls` lives in layout, not in a feature, because it combines `features/auth` and `features/profile`; this avoids a circular import.
- `src/components/common/`: shared app-level components that aren't shadcn primitives (e.g. `PagePlaceholder`).
- `src/lib/`: shared singletons/utilities (`createApiClient` + service clients, `queryClient`, `cn`).
- `src/stores/`: Zustand stores. `src/hooks/`: shared hooks. `src/types/`: shared types.
- File names are **kebab-case** (`random-number-card.tsx`, `use-random-number.ts`), matching shadcn. Exports are named (no default exports).
- Always import from `src` via the `@/` alias.

## CRUD pattern (`features/products`, `features/faqs`)

Copy this structure for new CRUD features.

- **Files:**
  - `types.ts`: the API shape, plus an `*Input` type with **only the writable fields**.
  - `validation.ts`: limits mirrored from the Django models, `validate*()`, `changed*Fields()` (a diff for PATCH), and the form ↔ API converters. Number fields are kept as strings in form state.
  - `api/`: `list(page)`, `create`, `update(id, changes)` (PATCH), and `delete`.
  - `hooks/`: `*Keys`, `use*(page)` with `keepPreviousData`, and `useSave*`/`useDelete*`, which invalidate `*Keys.all` on success.
  - `components/`: `*Manager` (the list), `*FormDialog` and `Delete*Dialog`.
- **Field rules (from configuration-service):**
  - Never send `id` or `business`; the backend fills in the user's business.
  - Product `quantity_sold` is read-only: display it, but never send it, or the API returns 400.
  - Editable: product `name`, `description`, `price` (a decimal string, sent with `toFixed(2)`), `quantity_available`, `quantity_on_hold`, `is_active`; FAQ `question`, `answer`.
  - If the backend limits change, update `PRODUCT_LIMITS` / `FAQ_LIMITS`.
- **Flow:** submit → client validation → `ConfirmDialog` (`@/components/common/confirm-dialog`) → mutation. The confirm dialog stays open with a pending state until the request finishes. On a 400, `getFormErrors()` (`@/lib/form-errors`) maps DRF `{field: [msg]}` errors onto fields, and `non_field_errors` becomes the form alert. **Every save and every delete must go through `ConfirmDialog`** (the user asked for this).
- **Form state:** the form content is remounted on each open (`{open && <Form />}`), so it always starts from the saved values. Edit mode sends only the changed fields, and **Save** is disabled when nothing changed.
- **Pagination:** `usePageParam()` keeps `?page=` in the URL, and `PaginationControls` renders the controls. If a page goes out of range (the API returns 404, e.g. after deleting the last item), the manager steps back a page.
- **Shared components:** `FormField` (label, hint/error, character counter) and `components/ui` `alert-dialog`, `table`, `textarea`, `switch` and `badge`. These were hand-written from shadcn because the CLI is blocked in this environment.

## Workflow editor (`features/workflow`)

- **API:** `GET /api/chat/configuration/` → `{id, business, config_json, last_updated}` for the user's business (no ID in the URL); `getChatConfiguration()` turns a 404 into `null` (no configuration yet → the editor starts from `DEFAULT_CONFIG`, a lone START_BLOCK). `PUT` with `{config_json}` upserts; `useSaveChatConfiguration` writes the response into the query cache.
- **`config_json`:** list of `{id, next_block_id, block_type, position_x, position_y}`. Block types are mirrored in `types.ts` from `configuration-service/chat_app/constants.py`; `blocks.ts` holds their labels/icons/colours. Exactly one `START_BLOCK`: it can't be added (not in the palette) or deleted (`deletable: false`, no × button), and has no input handle. New blocks get `crypto.randomUUID()` ids; existing ids (ints) are kept.
- **`flow.ts`** converts `config_json` ↔ React Flow nodes/edges. Node ids are `${typeof id}:${id}` (so `1` ≠ `"1"`); the original id is `node.data.blockId`. Each block has at most one outgoing edge (edge id `next:<source>`), so `onConnect` replaces the source's existing edge; self-connections are rejected (the backend rejects them too). Positions are rounded when converting back.
- **State:** nodes/edges live in `useNodesState`/`useEdgesState` (editor-local, not Zustand). Dirty = `flowToConfig(current)` JSON ≠ the saved config from the query. **Discard re-fetches** via the query's `refetch()` and resets from the result; it doesn't keep a local copy of the saved state (the user asked for this). Save and Discard both go through `ConfirmDialog`. `useBlocker` + `beforeunload` guard unsaved changes.
- **Details collection fields** (the user asked for this): `ChatBlock.fields?: DetailField[]` (`{key, label, type: text|number|email|phone, description?, required? (false = optional; only `false` is stored, see `normalizeDetailField`/`withRequired`), max_length? (text), min_value?/max_value? (number)}`; the dialog has a Required switch per detail and needs at least one required), stored in `node.data.fields`. `details.ts` mirrors the backend rules and limits (`DETAIL_LIMITS`, keep in sync with `chat_app/validators.py`), `DEFAULT_DETAIL_FIELDS` (name + email: new Details blocks get them via `createNewBlockNode`; a saved block without `fields` means the same, see `blockDetailFields`) and `PRESET_DETAIL_FIELDS` (+ phone, address). `flowToConfig` writes `fields` through `normalizeDetailField` (fixed key order, type-specific keys only) so the dirty check stays stable, and leaves `fields` out when the node has none. Clicking a Details node (`onNodeClick`; the × stops propagation) opens `DetailFieldsDialog`: preset switches + editable labels, custom rows (label, type, limits, hint), client-side validation, **Apply** only updates the node (the workflow's Save persists it). Saved keys never change (collected data is stored under them); new custom keys come from `keyFromLabel()` (preset keys are reserved). There's no frontend test runner; check pure logic with `npm run build` and, if needed, a throwaway script bundled with `node_modules/.bin/rolldown`.
- **Send message blocks** (`SEND_MESSAGE_BLOCK`): `ChatBlock.message` (required by the backend, ≤ `SEND_MESSAGE_MAX_LENGTH` = 4096, in `blocks.ts` with `DEFAULT_SEND_MESSAGE` for new blocks via `createNewBlockNode`), stored in `node.data.message` (`BlockSettings` in `flow.ts`, which `flowToConfig` writes back for Send message blocks only). Clicking one opens `SendMessageDialog` (textarea + counter, non-blank check; **Apply** only updates the node). The node shows a 3-line preview. In the Chat Sandbox debug panel, a step's `go_back_to` shows as "Went back to <key>", and `debug.sent_messages` lists what Send message blocks sent; an empty `reply_system_prompt` means the flow ended on one (no LLM reply).
- `WorkflowBuilder` shows the skeleton/error states; it only shows the error screen while there's no data at all, so a failed re-fetch never unmounts the editor and loses edits.

## Orders tab (`features/orders`, `OrdersBrowser`)

- **Read only.** `GET /orders/` → `DetailedPaginated<Order>`; `GET /orders/{id}/` for an order not on the current page (`useOrder(id, enabled)`; the dialog shows 403/404 messages). `Order` (`types.ts`, mirrored from configuration-service `checkout_app`): `order_status` (`ORDER_STATUSES`: `pending_payment` / `payment_received` / `order_completed`; labels/colours in `status.ts`), `order_data` `{items: [{product_id, name, unit_price, quantity}], details: Record<key, string | number>}`, `total` (decimal string), `is_sandbox`, `chat_session`.
- **URL state** (`useOrderParams`): `status`, `sandbox` (`include` default / `exclude` / `only`), `ordering` (`-created_time` default / `created_time` / `order_status`), `page`, `page_size`, `order` (open order). Defaults are left out; changing a filter resets `page`. Errors: 403 no business, 404 page past the end.
- Detail labels come from `useDetailLabels()` (`@/features/workflow`, shared with the Chats/Sandbox `ChatStateSummary`).
- The Chat Sandbox links to an order (`ChatStateSummary`: *Order #N* → `/orders?order=N`), and `useSendSandboxMessage` invalidates `orderKeys.all` and `productKeys.all` when a reply's `debug.order_id` is new (an order was placed: new order, stock changed).

## Chats tab (`features/chat-sessions`, `ChatSessionBrowser`)

- **Read only** (the user asked): no edit/delete here. `GET /chat/sessions/` → `DetailedPaginated<ChatSession>` (`@/types/api`: adds `total_pages`, `current_page`, `page_size`, `has_next`, `has_previous`). Query params follow the backend `ChatSessionFilter`: `sandbox` (`exclude` default / `include` / `only`), `search`, `chat_state_id`, `has_messages`, `last_chat_time_after|before`, `created_time_after|before`, `ordering`, `page`, `page_size` (10/20/50/100).
- **State lives in the URL** (`useChatSessionParams`): short names `search`, `state`, `messages`, `sandbox`, `last_from`/`last_to`/`created_from`/`created_to` (YYYY-MM-DD, sent as local start/end-of-day ISO via `toListParams`), `ordering`, `page`, `page_size`, and `chat` (open conversation). Defaults are omitted from the URL; invalid values fall back to defaults; changing any filter resets `page`. Search is debounced in the input's change handler (300 ms).
- `useChatSessions(params)` (`keepPreviousData`, key `chatSessionKeys.list(params)`). Step names come from `useChatSteps()` (the workflow's blocks via `@/features/workflow` `useChatConfiguration` + `BLOCK_META`). The conversation dialog uses `ChatMessageBubble perspective="business"` and shows `ChatStateSummary`. Errors: 403 no business, 404 page past the end ("Go to the first page"), 400 invalid URL filters ("Clear filters").
- `components/ui/native-select.tsx` is a hand-written styled native `<select>`.

## Chat Sandbox (`features/chat-sessions`)

- **Sandbox sessions only** (`is_sandbox`), all login-required and scoped to the user's business by the backend: `GET /chat/sandbox-sessions/?page=` (list), `POST /chat/sandbox-sessions/` `{display_name?, phone_number?}` (create; 400 `non_field_errors` without a chat configuration → `isMissingChatConfiguration()` → link to Workflow), `DELETE /chat/sandbox-sessions/{id}/`, `POST /chat/sandbox-sessions/{id}/messages/` `{message}` → reply `ChatMessage`. (The public `/chat/sessions/messages/` is for the future webhook; don't use it here.)
- **UI:** `ChatSandbox` → list (`SandboxSessionList`) + `SandboxChatWindow` (keyed by session id). The selected chat is `?session=<id>` (falls back to the most recent chat if missing/deleted). New chats are named `nextSandboxChatName()` ("Test chat N"). Drafts are kept per chat in the parent. Delete goes through `ConfirmDialog`.
- **Data:** `useSandboxSessions()` is a `useInfiniteQuery` (key `chatSessionKeys.sandboxList()`); messages come from the list data (there's no session-detail API). `useSendSandboxMessage(id)` has `mutationKey` `chatSessionKeys.sendSandboxMessage(id)`: it appends the customer message optimistically, appends the reply on success and invalidates the list on settle. Its callbacks live on the mutation, so they still run if the user switches chats; `useIsSendingSandboxMessage(id)` (`useIsMutating`) drives per-chat typing indicators across remounts.
- The send request overrides the client timeout (`SEND_MESSAGE_TIMEOUT_MS = 300_000`): a message makes several Ollama calls on the backend (the chat flow: one extraction per block passed, plus the reply), each allowed up to 120 s.
- **Chat flow state:** `ChatSession.chat_state_data` (`ChatStateData` in `types.ts`, mirrored from configuration-service `validate_chat_state_data`: optional `items` `[{product_id, name, unit_price (decimal string), quantity}]`, `items_confirmed`, `details` `Record<field key, string | number>`, `completed`, `order_id`) is read only here. `SandboxChatWindow` shows a strip under the header: the step (`useChatSteps().stepLabel(chat_state_id)`) + `ChatStateSummary` (`components/chat-state-summary.tsx`: order with a cents-based total, each detail labelled via `useDetailLabels()` (from the workflow's Details collection fields; falls back to the key), *Order confirmed* badge). It refreshes through the list re-fetch after each send (the optimistic update only adds messages).
- **Debug panel** (`SandboxDebugPanel`, open while `?debug` is in the URL; toggled by the bug button in `SandboxChatWindow`'s header, rendered by `ChatSandbox` beside the window): saved state (raw `chat_state_id`, its block from `useChatConfiguration()`, matched type-strictly, and `chat_state_data` as JSON) and the latest turn. The send response is `SandboxMessageReply` (`ChatMessage` + `debug: SandboxTurnDebug`); `useSendSandboxMessage` strips `debug` before adding the message to the list cache and puts it under `chatSessionKeys.sandboxTurnDebug(id)` (`gcTime: Infinity`, never fetched: `useSandboxTurnDebug` is a disabled query). So the latest turn is lost on reload, by design; the backend doesn't store it.

## WhatsApp card (`features/whatsapp`, `WhatsAppSettingsCard` on Home)

- **API** (configuration-service, the user's own business, no ID in the URL): `GET /configuration/whatsapp/` → `WhatsAppConfiguration` `{phone_number_id, display_phone_number, verified_name, webhook_url, verify_token, created_time, last_updated}` (`display_phone_number` / `verified_name` come from Meta, read only; shown by `ConnectedNumber`); `getWhatsAppConfiguration()` turns a 404 into `null` (not connected). `PUT` with `{phone_number_id, access_token?, app_secret?}` connects (201) or updates (200); `DELETE` disconnects. **The secrets are write-only**: never returned, so the form only holds a secret the owner is typing; empty secrets are left out of the PUT (`formValuesToWhatsAppInput`), which keeps the saved ones. Both are required when connecting. The user asked to keep only these three fields (no display phone number / WABA ID / App ID) and no `has_*` flags (a connection always has both secrets).
- **Hooks:** `whatsAppKeys`, `useWhatsAppConfiguration(enabled)` (enabled only when logged in), `useSaveWhatsAppConfiguration` / `useDeleteWhatsAppConfiguration` write the result (or `null`) into the cache.
- **UI:** the card handles its own auth (it's on Home, which isn't behind `RequireAuth`; `RequireAuth` would render a whole-page "Log in required" and change the tab title): logged out → `LoginDialog`; 403 → "not linked to a business". Connected → a "Webhook setup in Meta" panel (Callback URL + Verify token, `CopyField` with `navigator.clipboard`, plus the 3 Meta steps) above the form. One form for both states, remounted with `key={config.last_updated}` after each save. **Connected = locked** (the user asked): the inputs are disabled with **Edit** + Disconnect; Edit unlocks the Phone Number ID and shows **Save changes** + **Cancel** (Disconnect hidden; Cancel resets everything and locks again). **Saved secrets: masked + Replace** (the user chose this over "leave blank to keep"): `SavedSecret` shows a disabled input with dots (display only, never a form value; "saved and hidden" via `aria-describedby`), with a **Replace** button while editing; Replace (`replacing[field]`) swaps in an empty, focused password input + **Keep current** (clears the typed value); a Replace left empty is a validation error ("Enter the new …, or click Keep current.", `validateWhatsApp(values, isConnected, replacing)`), never a silent keep; a successful save remounts the form, so it's locked again; on an error it stays in edit mode. Not connected = always editable. **Connect** disabled until all three fields are filled (non-blank; the user asked, since all are required); **Save changes** disabled until something changes (`changedWhatsAppFields`). Format errors (digits only, no spaces) show on click. Connect, Save and Disconnect all go through `ConfirmDialog`; the backend checks every save with Meta, so Connect/Save show the pending label "Checking with Meta…", Meta's rejections arrive as 400 field errors (shown by `getFormErrors`) and an unreachable Meta as a 503 form error. Limits/rules in `validation.ts` (`WHATSAPP_LIMITS`, digits-only Phone Number ID ≤ 32, secrets no spaces, ≤ 1000 / ≤ 128), mirrored from configuration-service `configuration_app/models.py`.

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
- **Login guard: `RequireAuth`** (`features/auth/components/require-auth.tsx`, exported from `@/features/auth`).
  - It renders `children`, or `<Outlet />` when used as a layout route, when `selectIsAuthenticated` is true. Otherwise it shows a "Log in required" card with a `LoginDialog`.
  - It doesn't redirect: after login the page renders in place, and after logout the message replaces it.
  - **Protect pages by adding them to the pathless `{ element: <RequireAuth />, children: [...] }` group in `src/app/routes.tsx`**, currently Workflow, Product, Orders, FAQ, Chats and Chat Sandbox. Don't add auth checks inside page components.
  - It's UI only; the backend still enforces 401/403.
- **Not built yet:** an "expired session" toast, and role-based UI.

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
docker compose up --build   # from the repo root: frontend (Dockerfile.dev, hot reload via polling) + backend + DB
```

Before finishing a change, run `npm run build` and `npm run lint`. Both must pass.

## Environment notes for Claude

- The shadcn CLI needs `ui.shadcn.com`, which the Apple Claude Code sandbox blocks by default, so `npx shadcn add` fails until the user allows that domain. If it's blocked, write the component source by hand into `src/components/ui/`, following the existing files.
- The sandbox also blocks listening on local ports, so `npm run dev` / `preview` can't be smoke-tested from inside Claude. Use `npm run build` to verify.
