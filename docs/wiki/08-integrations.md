# Integrations

SynCiné talks to about ten external services, each wrapped in a small client in `backend/app/services/`. Only TMDB is required; everything else is optional and the app degrades gracefully when a service is missing or down. This page lists what each client is for, how it authenticates, how it caches, and which sources are unofficial. Clients are created lazily by `Ctx` (see [Backend](03-backend.md)) from the stored settings.

## Overview

| Client | Service | Used for | Auth | Status |
|---|---|---|---|---|
| `tmdb_client.py` | TMDB | Metadata, trending, upcoming, search, recommendations, streaming providers | API key (v3) or read token (v4) | **Required** |
| `trakt_client.py` | Trakt | Watchlist, history, ratings, favorites, recommendations, stats | OAuth: device code or PKCE | Recommended |
| `plex_client.py` | Your Plex server | Library, TMDB index, artwork, scrobble, ratings, admin dashboard | `X-Plex-Token` | Optional |
| `plex_auth.py` | plex.tv | PIN sign-in, server discovery, best connection, shared users | PIN → account token | Optional |
| `plex_account.py` | plex.tv providers | Account watchlist, watched/ratings outside your library, IMDb and Rotten Tomatoes scores, `watch.plex.tv` links | Account token | Optional |
| `seerr_client.py` | Seerr (Overseerr / Jellyseerr) | Title status, add requests | `X-Api-Key` | Optional |
| `letterboxd_client.py` | Letterboxd | Diary (watched titles, ratings) | None (public RSS) | Optional, read-only |
| `justwatch_client.py` | JustWatch | Direct links per service, new arrivals, charts | None | Optional, **unofficial**, off by default |
| `allocine_client.py` | AlloCiné, Filmstarts, SensaCine, Beyazperde | Cinema search and showtimes | None | Optional, **unofficial** |
| `news.py` | Film sites, YouTube | Film News feed | None; optional YouTube Data API key | Optional |

## Common rules

- **One HTTP client.** All clients use `services/http.py: http()`, a shared `httpx.AsyncClient` (15 s timeout, 5 s connect, follows redirects, user agent `syncine (self-hosted)`). Trakt sends its own `SynCine/<version>` user agent.
- **Errors.** Transport errors and HTTP errors become `ServiceError(service, French message, status)`. A missing configuration raises `NotConfigured(service)` (409). Callers that aggregate data catch `ServiceError` so one service never breaks a page.
- **Caching.** Responses go into the shared `TTLCache` (`services/cache.py`) under keys starting with the service name. Writes clear that service's cache (`cache.clear("trakt")`, `cache.clear("plex")`, `cache.clear("seerr")`). Saving any server-wide setting clears the whole cache.
- **Health.** `services/health.py: test_service()` runs a connection test per service (the Profile "Test" button and the 15-minute `services_health` job). A service that goes from OK to failing creates a `service` notification: to admins for server services (TMDB, Plex, Seerr, JustWatch), to the account for personal ones (Trakt, Letterboxd, cinemas).
- **Demo mode.** Without a TMDB key, `ctx.tmdb` is `MockTMDB` (`services/mock_data.py`), which returns real TMDB ids without images. `ctx.trakt_or_mock` and `ctx.plex_or_mock` do the same for pages dedicated to those services.

## TMDB — `tmdb_client.py`

- **Auth**: a key starting with `eyJ` is treated as a v4 read access token (`Authorization: Bearer`), anything else as a v3 `api_key` parameter.
- **What**: `trending`, `search_multi`, `discover`, `upcoming` (with regional release dates), `now_playing`, `on_the_air`, `recommendations`, `similar`, `detail` / `basic`, `season`, `collection`, `providers` (watch providers), `provider_catalog`, `regions`, `genres`.
- **Caching**: per call, from 10 min (search) to 7 days (genres, regions, provider catalogue); providers 12 h unless `fresh=True` (used by the availability job). Keys include a hash of the API key. At most 10 concurrent requests (`_sem`).
- **Streaming availability** comes from TMDB's watch providers, which are **powered by JustWatch data**. `services/enrich.py: stream_providers` keeps subscription, free and ads offers.
- **Attribution**: TMDB's terms require crediting it. The Profile's About section (`components/profile/About.jsx`) shows "This product uses the TMDB API but is not endorsed or certified by TMDB", and the README carries the TMDB logo. Keep both if you touch those files.

## Trakt — `trakt_client.py`

- **Auth**: OAuth without a client secret (Trakt deprecated it; `trakt_client_secret` is still sent if set, for old apps).
  - **Device code** (recommended for self-hosting): `POST /api/trakt/device/start`, then `POST /api/trakt/device/poll` until connected. The user types a code on Trakt's activation page.
  - **PKCE**: `GET /api/trakt/oauth/start` returns the authorize URL; Trakt redirects to `/api/trakt/oauth/callback` (needs an HTTPS `PUBLIC_URL`). State and verifier are stored in the account's settings.
- Tokens are refreshed automatically when less than 12 hours remain (`_ensure_fresh`, guarded by a lock); a 401 triggers one refresh and one retry. HTTP 420 (free-account limit) becomes a clear 409 error.
- **Per account**: the Trakt app id is a server setting, but tokens are per account. Cache keys include the account id.
- **Paging**: `_get_all` reads every page of list endpoints. Bulk writes use `add_many(path, refs)`, which reports `not_found` titles (used by the [sync engine](07-sync-engine.md)).
- `watchlist_limit()` reads `/users/settings` to detect free-account limits.

## Plex — three clients

| Client | Talks to | Token | Notes |
|---|---|---|---|
| `PlexClient` (`plex_client.py`) | Your Plex Media Server | Server token | `library()` (cached 10 min) and `index()` map items to TMDB ids from their `Guid`. `image()` relays artwork through `GET /api/plex/image` so the token stays server-side. `scrobble`, `unscrobble`, `rate`. Cache keys include a token hash, since results depend on the account |
| `plex_auth` (`plex_auth.py`) | `plex.tv/api/v2` | PIN, then account token | `create_pin` (mode `link`: code on plex.tv/link; mode `window`: app.plex.tv popup returning to `/plex-done.html`), `check_pin`, `list_servers`, `best_connection` (tests local, then remote, then relay URIs, plus the raw local IP when `*.plex.direct` DNS is blocked), `account_info`, `server_access`, `server_users` |
| `PlexAccount` (`plex_account.py`) | `discover.provider.plex.tv`, `metadata.provider.plex.tv` | Account token | Watchlist read/add/remove, watched and ratings for titles not in your library, `scores()` (IMDb, Rotten Tomatoes), `watch_url()` (`watch.plex.tv` link used to open the iOS app) |

`Ctx` exposes `plex` (member's own token, else the admin's), `plex_own` (member's token only: their watched state and ratings), `plex_admin` (admin token: full history, sessions, scans) and `plex_account`. The admin links the server once (`/api/plex/auth/pin`, `/api/plex/servers/select`); members get their own tokens when they sign in with Plex (see [Accounts and security](06-accounts-and-security.md)).

## Seerr — `seerr_client.py`

- **Auth**: `X-Api-Key` header on `<seerr_url>/api/v1`.
- `media_status()` (cached 2 min) and `request()` (TV requests default to all seasons). Status codes map to labels in `STATUS`.
- SynCiné never downloads anything. Requests go through `routers/requests.py`: sent directly to Seerr for admins and members with `can_request_direct`, otherwise queued for the admin.

## Letterboxd — `letterboxd_client.py`

- Reads `https://letterboxd.com/<username>/rss/` with `feedparser`; no login. Cached 30 min.
- Provides recent diary entries with TMDB ids, watched dates and ratings. Read-only: SynCiné never writes to Letterboxd, and the watchlist is not available over RSS.

## JustWatch — `justwatch_client.py` (unofficial)

- Uses JustWatch's **internal GraphQL API** (`apis.justwatch.com/graphql`). It can change without notice.
- Disabled by default; the admin enables it with `justwatch_enabled`. When it fails, the app falls back to TMDB data.
- Provides `offers()` (direct deep links per service), `new_titles()` (new arrivals on your services), `charts()` and `packages()`. JustWatch package ids match TMDB provider ids.
- Cache: 1 h to 7 days depending on the call.

## Cinemas — `allocine_client.py` (unofficial)

- Public JSON endpoints of Webedia's sites, chosen by country in `SITES`: France (AlloCiné), Germany (Filmstarts), Spain and Mexico (SensaCine), Turkey (Beyazperde).
- `search(query, country)` (cached 1 day) and `showtimes(theater_id, day, country)` (cached 30 min), with version labels (VO, VOST…) and booking links.
- Errors are reported as service `cinema`. Each account picks its own cinemas.

## Film News — `news.py`

- Feeds are parsed with `feedparser` and reduced to plain text (no HTML is ever rendered). Cache: 30 min per feed.
- `CATALOG` holds verified French and English sources; defaults depend on the UI language (`DEFAULTS`).
- Members can add any site (the feed is discovered in the page) or YouTube channel. Custom URLs are fetched with `safe_fetch` and must be verified through `POST /api/news/sources/custom` before they can be saved.
- YouTube uses the public channel feed. If it fails and the admin set `youtube_api_key`, the official YouTube Data API v3 is used as a fallback.
- Article images go through the signed relay (`/api/news/image`). See [Accounts and security](06-accounts-and-security.md#signed-image-relay).

## Adding an integration

1. Write `services/<name>_client.py` with a class that takes its credentials in `__init__`, uses `http()`, raises `ServiceError("<name>", ...)` and caches with keys starting with `"<name>"`.
2. Store its settings in `UserSettings` (nullable or with a default; see [Data model](05-data-model.md)). Add the field to `GLOBAL_FIELDS` if it is a server setting, and to `SECRET_FIELDS` if it is a secret.
3. Expose it as a `cached_property` on `Ctx` returning `None` when not configured.
4. Add a connection test in `services/health.py` (`SERVICES`, `LABELS`, `used_services`, `test_service`).
5. Add its label to `NotConfigured` in `services/errors.py` and the English translations of its messages.

## See also

- [Backend](03-backend.md)
- [Sync engine](07-sync-engine.md)
- [Accounts and security](06-accounts-and-security.md)
- [README data sources](../../README.en.md#data-sources)
