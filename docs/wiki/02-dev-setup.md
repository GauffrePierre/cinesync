# Development setup

To work on CinéSync you run two processes: the FastAPI backend with uvicorn on port 8000, and the Vite dev server for the frontend, which proxies `/api` to the backend. This page covers both, the environment variables, the test command and how to build the Docker image. You need **Python 3.12** and **Node 22** (the versions used by the `Dockerfile` and CI).

## Backend

```bash
cd backend
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt   # requirements-dev.txt only adds pytest
uvicorn app.main:app --reload --port 8000
```

- The database is created in `backend/data/cinesync.db` (default `data_dir` in `backend/app/config.py`).
- Settings are read from environment variables and from a `.env` file **in the current directory** (`SettingsConfigDict(env_file=".env")`), so in this setup `backend/.env`.
- Without a TMDB key, `ctx.tmdb` is a `MockTMDB` and the app shows demo data (`services/mock_data.py`). Add a free key in **Profile** to get real data.

### First run: the setup code

In the default `server` edition, the first screen asks you to create the admin account with a setup code printed in the logs:

```
Installation de CinéSync : code pour créer le compte administrateur -> ABCD-1234-EF56
```

For quick local hacking you can skip accounts entirely with the personal edition:

```bash
CINESYNC_MODE=personal uvicorn app.main:app --reload --port 8000
```

### Interactive API docs

The OpenAPI docs are off by default. Turn them on with `API_DOCS=true`; they are then at `/api/docs` (and the schema at `/api/openapi.json`).

## Frontend

```bash
cd frontend
npm install
npm run dev        # Vite on port 5173
```

`frontend/vite.config.js` proxies every `/api` request to `localhost:8000`. To point at another backend, set `VITE_API_TARGET`:

```bash
VITE_API_TARGET=http://localhost:9000 npm run dev
```

Because the proxy keeps the browser's `Host` header, the backend's same-origin check (see [Accounts and security](06-accounts-and-security.md)) accepts requests from the dev server without extra configuration.

### Testing the production build locally

The service worker is meant for the production build. To try the real thing without Docker:

```bash
cd frontend && npm run build
cp -r dist ../backend/static        # config.static_dir defaults to backend/static
```

Restart uvicorn: it now serves the SPA too (see the static route in `backend/app/main.py`). Remember to delete `backend/static` afterwards, or you will be looking at a stale build.

## Environment variables

### Read by the backend (`backend/app/config.py`)

Names are case-insensitive (pydantic-settings).

| Variable | Default | Purpose |
|---|---|---|
| `CINESYNC_MODE` | `server` | `server` (accounts, sign-in) or `personal` (one person, no sign-in) |
| `DATA_DIR` | `backend/data` (dev), `/app/data` (image) | Folder of `cinesync.db`, `secret.key` and the image cache |
| `STATIC_DIR` | `backend/static` (dev), `/app/static` (image) | Built frontend served by FastAPI |
| `PUBLIC_URL` | empty | Public `https://` address: Trakt OAuth redirect, secure cookies, origin check, HSTS and HTTPS redirect host |
| `HSTS_SECONDS` | `0` | Sends `Strict-Transport-Security` on the `PUBLIC_URL` host only |
| `CORS_ORIGINS` | empty | Extra allowed origins (comma-separated), for CORS and the same-origin check |
| `API_DOCS` | `false` | Enables `/api/docs` |
| `NOTIFICATION_INTERVAL_HOURS` | `24` | Interval of the watchlist availability job |
| `LOG_LEVEL` | `INFO` | Python logging level |

### Read by the container or Compose

| Variable | Read by | Purpose |
|---|---|---|
| `FORWARDED_ALLOW_IPS` | uvicorn (`--proxy-headers`) | Proxies whose `X-Forwarded-*` headers are trusted. Image default: `127.0.0.1,172.16.0.0/12` |
| `PUID` / `PGID` | `docker/entrypoint.sh` | Owner of the data folder; the server then runs as this user (default `99`/`100`) |
| `TZ` | container | Time zone (Compose default `Europe/Paris`) |
| `DATA_PATH`, `CINESYNC_PORT`, `CINESYNC_BIND` | `docker-compose.yml` | Host data folder, host port, bind address |
| `VITE_API_TARGET` | `vite.config.js` | Backend URL for the dev proxy |

The root `.env.example` documents the variables for a Docker Compose deployment. Service keys (TMDB, Trakt, Plex, Seerr…) are never environment variables: they are entered in the interface and stored in the database.

## Editions: `server` vs `personal`

| | `server` | `personal` |
|---|---|---|
| Sign-in | Required (password or Plex) | None, unless the owner sets a password in Profile |
| Accounts, admin area, requests queue | Yes | No (`require_server_mode` returns 409) |
| Setup code | Printed until an admin can sign in | Never (`setup_required()` is `False`) |
| Exposure | LAN, Tailscale, or Internet behind HTTPS | Trusted networks only |

The switch is `config.cinesync_mode`. See [Accounts and security](06-accounts-and-security.md) for details.

## Running the tests

```bash
cd backend
python -m pytest -q
```

This is exactly what CI runs. The test suite uses its own temporary data folder (`tests/conftest.py` sets `DATA_DIR` before importing the app), so it never touches your dev database. The frontend has no unit tests; its check is `npm run build`. More in [Testing](10-testing.md).

## Building the Docker image

```bash
docker build -t cinesync:dev --build-arg VERSION=dev .
docker run --rm -p 3000:8000 -v "$PWD/data:/app/data" -e CINESYNC_MODE=personal cinesync:dev
```

Or, with the repository's Compose file (reads `.env`):

```bash
cp .env.example .env     # adjust DATA_PATH, CINESYNC_PORT, PUBLIC_URL…
docker compose up -d --build
```

The image runs `docker/entrypoint.sh`, which fixes ownership of `/app/data` (`chmod 700`, files `600`) and drops root privileges with `setpriv` before starting uvicorn.

## Editor

`.vscode/settings.json` only sets `python.terminal.useEnvFile`. There is no enforced formatter or linter config in the repository; follow the style of the surrounding code (see [Contributing](12-contributing.md)).

## See also

- [Architecture](01-architecture.md)
- [Testing](10-testing.md)
- [Release and deploy](11-release-and-deploy.md)
- [Accounts and security](06-accounts-and-security.md)
