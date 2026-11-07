# mock_whatsapp

A stand-in for WhatsApp and Meta, to try the whole chat locally: you chat as a customer (any phone number you pick) with the sample businesses, and the assistant's replies come back, without a real WhatsApp account or Meta app. FastAPI, a server-rendered page (Jinja2), vanilla JavaScript and CSS, and a local SQLite file. Runs on port **9000**, in docker compose (`mock-whatsapp`) or on your machine.

## How it fits in

```
mock_whatsapp ──(1) Meta's webhook, signed──▶ messaging-ingester ──▶ Pub/Sub ──▶ messaging-service (chat flow)
      ▲                                                                                  │
      └──(3) fake Graph API: POST /v26.0/{phone_number_id}/messages ◀── configuration-service ◀──(2) send
```

1. **You send a message:** the mock POSTs Meta's webhook body to `http://localhost:8002/webhook/{business_id}`, exactly as Meta does (`app/meta.py`): `{"object": "whatsapp_business_account", "entry": [{"changes": [{"field": "messages", "value": {"metadata": {"phone_number_id"}, "contacts", "messages": [{"from", "id": "wamid.…", "timestamp", "type": "text", "text": {"body"}}]}}]}]}`, with `X-Hub-Signature-256: sha256=<HMAC of the body with the business's App Secret>`.
2. messaging-ingester checks the signature with configuration-service and publishes the message; messaging-service answers it with the chat flow and sends the reply through configuration-service's internal send endpoint (which holds the access token).
3. **The reply comes back:** configuration-service calls the Graph API at `META_GRAPH_API_URL`, here the mock's fake one (`app/graph_api.py`): `POST /v26.0/{phone_number_id}/messages` with `Authorization: Bearer <access token>`, answered like Meta (`{"messages": [{"id": "wamid.…"}]}`). The page polls and shows it. `GET /v26.0/{phone_number_id}` answers the credentials check, so connecting WhatsApp in the frontend works against the mock too.

The businesses and their dummy credentials (`businesses.json`) are configuration-service's fixture `sample_whatsapp_configurations` (one connection per sample business): keep them in step.

## Running it

`docker compose up` (from the repo root) runs it as `mock-whatsapp` on http://localhost:9000 (`Dockerfile`), with `INGESTER_URL=http://messaging-ingester:8002`, its database in the `mock-whatsapp-data` volume, and configuration-service's `META_GRAPH_API_URL` pointed at it (`http://mock-whatsapp:9000/v26.0`).

Or on your machine (stop the container first: `docker compose stop mock-whatsapp`):

```bash
cd mock_whatsapp
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt   # once
.venv/bin/python run.py                                              # http://localhost:9000
```

Then, for replies to reach it, set configuration-service's `META_GRAPH_API_URL` = `http://<this machine, as seen from Docker>:9000/v26.0` in the root `.env`.

On the page: pick who you are under **Chatting as** (or **＋** for a new customer: a name, and a number or a random Singapore one; each number is its own WhatsApp id), pick a business on the left, and chat. The **＋** button (Photo or Document) sends a **photo or document**: only its name, type and size go anywhere (no file is uploaded or kept), as Meta's `image` / `document` webhook (the text you type is the caption), and the chat shows a placeholder. Their details are kept in memory only (`app/media.py`), so after a restart they show as "Attachment". The project doesn't answer them yet (messaging-service skips messages that aren't text). ✓✓ means the webhook took the message; a red `!` means it failed (hover for why). **Delete all messages** clears the mock's history (not the project's database).

| Variable | Default | |
| --- | --- | --- |
| `PORT` / `HOST` | `9000` / `0.0.0.0` | 0.0.0.0, so the containers can reach the fake Graph API |
| `INGESTER_URL` | `http://localhost:8002` | messaging-ingester (where the webhooks go) |
| `MOCK_WHATSAPP_DB` | `mock_whatsapp.sqlite3` | The local database (git-ignored) |
| `MOCK_WHATSAPP_BUSINESSES` | `businesses.json` | The businesses' numbers and dummy credentials |

## Tests

```bash
.venv/bin/python -m unittest -v
```

The webhook payload and its signature, sending (and a failed webhook), the fake Graph API (stored replies, Meta's responses and errors: bad token 190, bad `appsecret_proof`, unknown number), new customers and the page.

## Structure

```
mock_whatsapp/
├── app/
│   ├── __init__.py     # create_app()
│   ├── config.py       # settings, businesses.json
│   ├── db.py           # SQLite: customers, messages
│   ├── media.py        # photos / documents: their metadata, in memory only
│   ├── meta.py         # Meta's webhook payload + signature, POST to the ingester
│   ├── graph_api.py    # the fake Graph API (replies come in here)
│   └── routes.py       # the page and its JSON API
├── templates/index.html
├── static/             # app.js (send, poll for replies), style.css (WhatsApp Web look)
├── businesses.json
├── tests/
├── Dockerfile
└── run.py
```
