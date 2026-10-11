# CS5224 Project

![Architecture Diagram](docs/arch-diagram.png)

## Running locally with Docker

```bash
docker compose up --build
RESET_DB=true docker compose up --build   # reset the database to the sample data
```

| Service | URL |
| --- | --- |
| frontend-app (Vite dev server, hot reload) | <http://localhost:5173> |
| configuration-service (Django API, Swagger at `/api/docs/`) | <http://localhost:8000> |
| messaging-service (Gunicorn: LLM chat, and the pull consumer of the ingester's messages, Swagger at `/docs`) | <http://localhost:8001> |
| messaging-ingester (WhatsApp webhook → Pub/Sub, Swagger at `/docs`) | <http://localhost:8002> |
| Pub/Sub emulator (in memory) | `localhost:8085` |
| PostgreSQL | `localhost:5433` (user/password `postgres`) |

To see the WhatsApp messages the ingester published: `docker compose exec messaging-ingester python scripts/pull_debug.py`
(see `messaging-ingester/README.md`). messaging-service pulls them too, on its own subscription, and logs each one:
`docker compose logs -f messaging-service` (see `messaging-service/README.md`).

notification-job runs every hour (cron, no port): `docker compose logs -f notification-job`. To run it once now:
`docker compose exec notification-job python run.py` (see `notification-job/README.md`).

After changing `frontend-app/package.json`, rebuild it: `docker compose up --build -V frontend-app`
(`-V` recreates the `node_modules` volume so the new packages are used).
