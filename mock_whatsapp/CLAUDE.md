# CLAUDE.md: mock_whatsapp

A local stand-in for WhatsApp and Meta (the user asked), for end-to-end chats without them: not deployed yet; docker-compose runs it (`mock-whatsapp`, `Dockerfile`; SQLite in the `mock-whatsapp-data` volume). See the README for the flow.

- **Stack (the user chose):** FastAPI, server-rendered Jinja2 (`templates/index.html`), vanilla JavaScript (`static/app.js`: send, poll `GET /api/messages?after=` every 1.5 s) and vanilla CSS in WhatsApp Web's style (`static/style.css`), local SQLite (`app/db.py`, plain `sqlite3`). Port 9000, `0.0.0.0`.
- **It must behave like Meta.** `app/meta.py` builds the `messages` webhook exactly as Meta does and signs the exact bytes (`X-Hub-Signature-256`, HMAC-SHA256 with the App Secret); `app/graph_api.py` answers like the Graph API (`POST /v26.0/{phone_number_id}/messages`, `GET /v26.0/{phone_number_id}`; Bearer token, `appsecret_proof`, Meta's error shape and codes). When changing either, keep it to Meta's documented format: messaging-ingester and configuration-service must not need anything mock-specific.
- `businesses.json` mirrors configuration-service's fixture `sample_whatsapp_configurations` (dummy `access_token` / `app_secret` / `verify_token` per business, plus a dummy `waba_id`). Change both together.
- Customers are identified by `wa_id` (digits, no "+"), as WhatsApp does; the ingester turns it into E.164.
- Tests: `python -m unittest -v` (temporary database and businesses file, the ingester mocked with `httpx.MockTransport`). The cross-service check (Django's signature check, the ingester's parser, configuration-service's `meta_api` against the fake Graph API) was run by hand; repeat it after changing the formats.
