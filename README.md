# CS5224 Project

![Architecture Diagram](docs/arch-diagram.png)

## Running locally with Docker

```bash
docker compose up --build
RESET_DB=true docker compose up --build   # reset the database to the sample data
```

After changing `frontend-app/package.json`, rebuild it: `docker compose up --build -V frontend-app`
(`-V` recreates the `node_modules` volume so the new packages are used).
