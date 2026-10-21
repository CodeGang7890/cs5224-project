# CS5224 Project

![Architecture Diagram](docs/arch-diagram.png)

## Running locally with Docker

Set up the [local LLM](#local-llm-ollama) first: the chat features need it.

```bash
docker compose up --build
RESET_DB=true docker compose up --build   # reset the database to the sample data
```

| Service | URL |
| --- | --- |
| frontend-app (Vite dev server, hot reload) | <http://localhost:5173> |
| mock_whatsapp (WhatsApp stand-in, run on your machine: see [below](#trying-whatsapp-end-to-end-mock_whatsapp)) | <http://localhost:9000> |
| configuration-service (Django API, Swagger at `/api/docs/`) | <http://localhost:8000> |
| payment-ingester (Gunicorn: creates Xendit Payment Sessions for the chat flow, receives Xendit webhooks → Pub/Sub payment-events, Swagger at `/docs`) | <http://localhost:8001> |
| messaging-ingester (WhatsApp webhook → Pub/Sub, Swagger at `/docs`) | <http://localhost:8002> |
| processing-service (Gunicorn: pull consumer of the payment events, Swagger at `/docs`) | <http://localhost:8003> |
| messaging-service (Gunicorn: the chat flow behind the Chat Sandbox, LLM chat, and the pull consumer of the ingester's messages, Swagger at `/docs`) | <http://localhost:8004> |
| Ollama (the LLM, on your machine, not in Docker: see [Local LLM](#local-llm-ollama)) | <http://localhost:11434> |
| Pub/Sub emulator (in memory; `pubsub-init` creates the topics `whatsapp-inbound-messages` and `payment-events`) | `localhost:8085` |
| PostgreSQL | `localhost:5433` (user/password `postgres`) |

To see the WhatsApp messages the ingester published: `docker compose exec messaging-ingester python scripts/pull_debug.py`
(see `messaging-ingester/README.md`). messaging-service pulls them too, on its own subscription, and answers each one with the chat flow and sends the reply (try it with mock_whatsapp, below):
`docker compose logs -f messaging-service` (see `messaging-service/README.md`).

To publish dummy payment events (`payment_reference`, `status` success / fail, and the order / booking's `amount`) to the `payment-events` topic, with the stack running (by default for random orders / bookings still pending payment):

```bash
cd payment-ingester && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt   # once
.venv/bin/python scripts/publish_dummy_payments.py --count 5
```

processing-service pulls them, checks the amount, and updates those orders / bookings (payment received or failed, and the booking's calendar): `docker compose logs -f processing-service` (see `payment-ingester/README.md`).

notification-job runs every hour (cron, no port) and logs the payment and appointment reminders it would send: `docker compose logs -f notification-job`. To run it once now:
`docker compose exec notification-job python run.py` (see `notification-job/README.md`).

After changing `frontend-app/package.json`, rebuild it: `docker compose up --build -V frontend-app`
(`-V` recreates the `node_modules` volume so the new packages are used).

## Trying WhatsApp end to end (mock_whatsapp)

`mock_whatsapp/` stands in for WhatsApp: you chat as a customer with the sample businesses, and the assistant's replies come back through the whole system.

Start the mock server (on your machine):

```bash
cd mock_whatsapp
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt   # once
.venv/bin/python run.py
```

It opens on <http://localhost:9000>.

## Xendit payments

The chat flow creates a Xendit payment link after an order or booking is confirmed. The customer pays on Xendit's hosted page, and Xendit's webhook updates the order / booking through `payment-ingester` → Pub/Sub → `processing-service`.

1. Copy the root env template and fill in your Xendit values:

   ```powershell
   Copy-Item .env.example .env
   ```

   Set at least:

   ```env
   XENDIT_SECRET_KEY=your-xendit-secret-key
   XENDIT_WEBHOOK_SECRET=your-xendit-webhook-token
   ```

   Leave `XENDIT_SUCCESS_URL` and `XENDIT_FAILURE_URL` empty for local development (Xendit then uses its own hosted result page).

2. Expose the local webhook with a public HTTPS tunnel (for example ngrok):

   ```bash
   ngrok http 8001
   ```

3. In the Xendit dashboard:
   - add the ngrok URL as the webhook callback URL (`https://…/webhook`)
   - set the webhook token to the same value as `XENDIT_WEBHOOK_SECRET`
   - enable `payment_session.completed` and `payment_session.expired` (optionally `payment.failure`, `payment.capture`, `payment.succeeded`)

4. Restart the stack so the new `.env` values are used:

   ```bash
   docker compose up --build
   ```

The business payment dashboard is at `http://localhost:5173/orders/payment`. Public customer result pages are available at `/payment/success` and `/payment/failed`, but they are only used when `XENDIT_SUCCESS_URL` / `XENDIT_FAILURE_URL` are set to HTTPS URLs.

See `docs/XENDIT_INTEGRATION.md` for the full flow, failure paths, and GCP Secret Manager notes.

## Local LLM (Ollama)

The chat assistant (messaging-service) uses a local LLM through [Ollama](https://ollama.com), running **on your machine, not in Docker**. A Docker VM usually has too little memory for the model (it needs about 5 GB), and Ollama on the host can use the GPU.

1. **Install Ollama:** download it from <https://ollama.com/download>, or `brew install ollama` on macOS.
2. **Download the model** (about 4.7 GB, once):

   ```bash
   ollama pull qwen2.5:7b-instruct-q4_K_M
   ```

   This is the model both services use (`OLLAMA_MODEL` in `configuration-service/chat_app/llm.py` and `messaging-service/app/config.py`).
3. **Start Ollama so the containers can reach it.** By default it only listens on `127.0.0.1`, which Docker can't reach, so listen on all interfaces:

   ```bash
   OLLAMA_HOST=0.0.0.0 ollama serve
   ```

   Keep it running while you use the app. Quit any Ollama that's already running first (the app, or `brew services stop ollama`). With the Ollama desktop app, you can instead run `launchctl setenv OLLAMA_HOST 0.0.0.0` once, then quit and reopen the app. Check it with `lsof -nP -iTCP:11434 -sTCP:LISTEN`: it should show `*:11434`, not `127.0.0.1:11434`.
4. **Tell docker-compose where it is.** The default is `http://host.docker.internal:11434`, which works with Docker Desktop. Other Docker setups may need your machine's address on the VM's network, set in a `.env` file in the repo root (git-ignored). docker-compose reads it automatically:

   ```bash
   echo "OLLAMA_HOST=http://192.168.64.1:11434" > .env   # e.g. a vessel VM, which runs at 192.168.64.2
   docker compose up -d messaging-service
   ```

5. **Check that the containers reach it:**

   ```bash
   docker compose exec messaging-service python -c "import urllib.request; print(urllib.request.urlopen('http://host.docker.internal:11434/api/tags', timeout=5).read()[:80])"
   ```

   Use the address from your `.env`, if you set one. It should print JSON listing the model. If it times out, allow incoming connections for `ollama` in your firewall (macOS: System Settings → Network → Firewall).

If the Chat Sandbox says "Could not connect to Ollama", repeat steps 3 to 5.

## CI

GitHub Actions (`.github/workflows/ci.yml`) runs on every pull request to `main` and every push to `main`:

- configuration-service: checks, migrations, fixtures and tests (PostgreSQL)
- frontend-app: lint, type-check and build
- messaging-ingester, messaging-service, payment-ingester, processing-service, notification-job and mock_whatsapp: `python -m unittest` (messaging-ingester with a Pub/Sub emulator)

The ruleset in `.github/rulesets/main.json` requires the **CI passed** check (green only when every job is) before anything can be merged to `main`. To apply it: repository Settings → Rules → Rulesets → New ruleset → Import a ruleset.
