# File map (AI reference)

One line per file: responsibility → key symbols. Paths relative to repo root.

## Root
- `Dockerfile` → 2 stages: node builds `frontend/dist` → python:3.12-slim serves API + SPA (`/app/static`); runs as `PUID:PGID` via `docker/entrypoint.sh` (drops root, data dir 700 / files 600); `FORWARDED_ALLOW_IPS` default `127.0.0.1,172.16.0.0/12`.
- `docker-compose.yml` → single service `cinesync`, port `${CINESYNC_BIND}:${CINESYNC_PORT}:8000`, volume `${DATA_PATH}:/app/data`. Optional untracked `docker-compose.override.yml` for extra binds (proxy container).
- `.env.example` → all env vars (see `backend/app/config.py`).
- `.github/workflows/docker.yml` → on tag `v*.*.*`/manual: pytest + vite build, then multi-arch image to `ghcr.io/<owner>/cinesync` (actions pinned by SHA). `.github/dependabot.yml`, `.github/FUNDING.yml`.
- `unraid/cinesync.xml` → Unraid template. `SECURITY.md`, `LICENSE` (AGPL-3.0), `README.md` (FR) / `README.en.md`.
- `docs/wiki/` human dev wiki · `docs/guides/{fr,en}/` user starter guides · `docs/ai/` this folder · `docs/screenshots/` README images (demo data).

## Backend `backend/app/`
- `__init__.py` → `__version__` (single source).
- `main.py` → FastAPI app; middlewares: gzip, optional CORS (`CORS_ORIGINS`), security headers + CSP, HSTS only on `PUBLIC_URL` host, HTTP→HTTPS redirect on public host, same-origin check for unsafe methods; mounts routers (`auth` public, others `Depends(require_ready)`); `/api/health`; SPA static route (path-traversal safe, cache headers).
- `config.py` → `Config` (pydantic-settings): `data_dir`, `static_dir`, `cinesync_mode`, `api_docs`, `hsts_seconds`, `public_url`, `cors_origins`, `notification_interval_hours`, `log_level`.
- `database.py` → engine (SQLite WAL), `SessionLocal`, `Base`, `UserScoped` mixin, `bind_user`, ORM events (`_scope_to_user`, `_assign_user`), `_add_missing_columns`, `_rebuild_for_users` (`_REBUILD_FOR_USERS`), `init_db` (creates admin id 1, setup code), `setup_required`.
- `scheduler.py` → APScheduler jobs: health 15 min, `pull_library` 30 min (sync + history import, per user), availability (24 h), new episodes (6 h); `for_each_user(job)`, `availability_one`, `episodes_one`.
- `models/` → `user.py` (`User`, `AuthSession`), `user_settings.py` (`UserSettings`: per-user row; global fields on row 1), `media_state.py` (`MediaState`: per-title merged state, `*_sources` JSON), `swipe_history.py`, `watch_event.py` (history for stats; plex events carry `plex_account_id`), `notification.py`, `media_request.py`. All personal ones inherit `UserScoped`.
- `schemas/settings.py` → `SettingsOut.from_model(s, admin)` (masks secrets, hides server URLs from members), `SettingsUpdate`, `SECRET_FIELDS`. `schemas/media.py`.
- `routers/` → `auth` (setup, login, logout, password, profile, Plex login), `admin` (users, allowed Plex accounts, Plex dashboard/scan/stats), `user` (settings, status, tests, meta, stats), `media` (aggregated title page, highlights, suggestions), `library` (state keys, watchlist/watched/rating/like/dislike, sync), `tmdb`, `trakt` (device code + PKCE OAuth, reads), `plex` (library, images, server connection [admin], watch-link), `episodes`, `tonight`, `swipe`, `search`, `notifications`, `requests`, `cinema`, `justwatch`, `letterboxd`, `seerr`, `news`. Endpoint list: `docs/ai/api.md`.
- `services/`
  - `context.py` → `Ctx` (db, `EffectiveSettings`, user) with cached clients `tmdb`, `plex` (read; own token, or the server's for admins only — `None` for members without Plex), `plex_own` (member's own token: watched/progress/writes), `plex_admin`, `plex_account`, `trakt`, `trakt_app`, `seerr`, `letterboxd`, `justwatch`; `GLOBAL_FIELDS`, `SHARED_ID=1`, `settings_for`, `ctx_for` (scheduler), `get_ctx`, `public_base_url`.
  - `auth.py` → scrypt hashing, `RateLimiter` (keys `pair:`, `ip:`, `user:`, `all:`), sessions (`open_session`, `close_session`, `close_all_sessions`, `session_user`), deps `current_user`, `require_ready`, `require_admin`, `require_server_mode`, `personal_mode`.
  - `backup.py` → SQLite online backup → gzip in `data/backups` (600), `rotate`, `run_automatic` (scheduler `db_backup`, hourly check, 23 h), `path_of` (name whitelist).
  - `totp.py` → 2FA: RFC 6238 codes (`code_at`, `verify` with replay counter), `provisioning_uri`, `qr_svg` (segno), recovery codes (sha256, single use).
  - `library_sync.py` → `pull` (collect + merge + optional two-way), `act` (apply one action everywhere), `_two_way` (safeguards), `preview`, `state_of`, `get_row`; per-user `_last_pull`, `_pull_locks`, `_failed_once`.
  - `history.py` → imports (Plex server-wide with account→user mapping, Trakt, Letterboxd), `assign_plex_events`, `stats`, `events_between`.
  - `health.py` → service tests, state per (user|global, service), down notifications (`GLOBAL_SERVICES` → admins).
  - Clients: `tmdb_client.py`, `trakt_client.py` (token refresh, pagination `_get_all`), `plex_client.py` (server; cache per token), `plex_account.py` (plex.tv: watchlist, scrobble, ratings, `watch_url`), `plex_auth.py` (PIN, resources, `server_users`, `account_info`), `seerr_client.py`, `letterboxd_client.py` (RSS), `justwatch_client.py` (unofficial GraphQL), `allocine_client.py` (unofficial, FR/DE/ES/TR/MX).
  - `news.py` → film news catalog (`CATALOG`, `DEFAULTS`), feed parsing to plain text, YouTube (RSS, API fallback), `resolve` (custom sources), image relay (`proxied`, `valid_signature`, `image`, disk cache). `safe_fetch.py` (SSRF-safe GET). `secret.py` (`server_secret()` in data dir).
  - Others: `cache.py` (TTL cache, keys start with service name), `http.py` (shared httpx client, `USER_AGENT`), `errors.py` (`ServiceError`, `NotConfigured`), `enrich.py` (providers/plex badges, `refs_to_items`, `plex_keys`), `suggestions.py`, `mock_data.py` (demo data without TMDB key).
- `backend/tests/` → `conftest.py` (temp DB, fakes), `test_library_sync.py`, `test_accounts.py` (auth, isolation, editions, security regressions), `test_admin_plex.py`, `test_news.py`, `test_plex_links.py`.

## Frontend `frontend/src/`
- `main.jsx` → React root, QueryClient defaults, self-hosted Inter font, PWA registration (`virtual:pwa-register`, hourly/visibility update checks).
- `App.jsx` → auth gate (`useMe`: splash / setup / login / forced password change / app) + routes.
- `pages/` → `Discover`, `Upcoming`, `News`, `Library` (Plex only), `Tonight`, `Watchlist`, `MediaDetail`, `Profile`, `Stats`, `Swipe`, `Admin`, `Login` (Setup, Login, PasswordForm, ForcePasswordChange, Splash).
- `components/layout/` → `AppLayout`, `Sidebar` (nav, services health, version), `BottomBar` (mobile), `TopBar`, `nav.js` (`NAV_ITEMS`, `useNavItems` hides items needing an absent service).
- `components/media/` → `MediaCard`, `PosterActions`, `MediaRow`, `MediaGrid`, `HeroCarousel`/`HeroSection`, `PlatformFilter`, `Poster`; `detail/` (`Availability`, `SeriesTracker`, `People`, `Trailer`).
- `components/admin/` → `PlexDashboard`, `UsersPanel`. `components/profile/` → `ConnectionCard`, `PlexConnect`, `TraktConnect`, `SyncPanel`, `CinemaPicker`, `PlatformPicker`, `RequestsPanel` (scope mine/all), `HiddenTitles`, `NotificationSettings`, `About` (`Support`, `About`).
- `components/ui/` → `Button`, `Modal`, `Tabs` (translates labels), `EmptyState`, `Skeleton`, `Toaster`, `PlatformBadge`, `StarRating`, `WatchlistButton`, `WatchLink` (opens native apps), `AppChooser` (iOS app/browser sheet).
- `hooks/` → `useMedia.js` (all queries/mutations; optimistic `library-keys`), `useAuth.js` (`useMe`, `useCurrentUser`, `useIsAdmin`, `usePersonal`, `useResetSession`), `useTheme.js`, `useSyncOnOpen.js`, `useDebounce.js`, `useSwipeGesture.js`.
- `services/` → thin API wrappers: `api.js` (fetch, errors translated, 401 event), `auth.js`, `admin.js`, `user.js`, `library.js`, `media/tmdb.js`, `trakt.js`, `plex.js`, `requests.js`, `news.js`, `notifications.js`, `search.js`, `swipe.js`.
- `i18n/` → `index.js` (`translate`, `t`, `useT`, `currentLocale`, `fmtNumber`, `UI_LANGUAGES`), `en/*.js` dictionaries merged in `en/index.js`.
- `lib/` → `format.js` (dates, relative time [UTC-safe], labels), `platforms.js`, `appLinks.js` (Android intents, iOS app links; Plex = watch.plex.tv links only, real `href` taps), `project.js` (repo, license, Ko-fi URL).
- `store/` → `uiStore.js` (filters, toasts, search), `settingsStore.js` (theme, UI language; persisted).
- `public/` → `manifest.json`, icons, `plex-done.html`, `theme-init.js` (pre-render theme, no inline script).
