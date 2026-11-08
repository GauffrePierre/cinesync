# AGENTS.md — CinéSync for AI coding agents

Dense, rule-first context for AI assistants (Claude Code, Copilot, Cursor, Codex…). Humans: see `docs/wiki/`.
Detailed AI notes: `docs/ai/` → `map.md` (file map), `api.md` (all endpoints), `invariants.md` (must-not-break), `recipes.md` (how-to).

## Project
Self-hosted PWA for film lovers: streaming availability, local cinema showtimes, watchlist/watched/ratings synced across Trakt, Plex, Letterboxd, recommendations, film news. One Docker image: FastAPI serves `/api/*` + the built SPA. SQLite. License AGPL-3.0.

- Backend: Python 3.12, FastAPI, SQLAlchemy 2 (typed `Mapped`), SQLite (WAL), APScheduler, httpx, feedparser, Pillow. `backend/app/`.
- Frontend: React 18, Vite, Tailwind v4, TanStack Query, Zustand, react-router v7, motion, lucide-react, vite-plugin-pwa. `frontend/src/`.
- Editions: `CINESYNC_MODE=server` (admin + family accounts, sign-in) | `personal` (one user, optional password).

## Commands
```bash
cd backend && python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt pytest
uvicorn app.main:app --reload --port 8000        # API on :8000, DB in backend/data/
python -m pytest -q                               # must stay green
cd frontend && npm install && npm run dev         # :5173, proxies /api to :8000
npx vite build                                    # must build without errors
docker compose up -d --build                      # full image (see .env.example)
```

## Hard rules (read before editing)
1. **Per-user data isolation.** Personal tables inherit `UserScoped` (`backend/app/database.py`). Every ORM SELECT/UPDATE/DELETE in a session bound with `bind_user(db, user_id)` is auto-filtered to that user, and new rows get `user_id` automatically. `db.get()` is filtered too. Use `.execution_options(all_users=True)` **only** in admin/global code, and never return other users' rows to a member. New personal table ⇒ inherit `UserScoped`; if its unique constraint must include `user_id` on existing DBs, add the table to `_REBUILD_FOR_USERS`.
2. **Shared vs per-user settings.** `UserSettings` has one row per user (id = user id). Fields in `GLOBAL_FIELDS` (`services/context.py`) live on row 1 (server-wide: TMDB key, Plex server, Seerr, JustWatch, Trakt app id, YouTube key) and are routed by `EffectiveSettings`. Members must not write them: `ADMIN_FIELDS` check in `routers/user.py`. Secrets are listed in `SECRET_FIELDS` (`schemas/settings.py`) and are never returned in clear (masked preview, admin only).
3. **Auth.** All routers except `auth` are mounted with `Depends(require_ready)` (`main.py`). Admin-only: `require_admin`. Server-only features: `require_server_mode`. Unsafe methods are rejected unless `Origin` equals the request origin / `PUBLIC_URL` (same-origin middleware). State-changing endpoints must be POST/PUT/PATCH/DELETE, never GET.
4. **Outbound requests from user input** (custom feeds, URLs) go through `services/safe_fetch.py` (public IPs only, redirects re-checked, size/time limits). Remote images shown to users are relayed via signed URLs (`services/news.py: proxied/valid_signature`). Never fetch arbitrary URLs with the shared `http()` client.
5. **Frontend security.** No `dangerouslySetInnerHTML`, no inline `<script>`. CSP is defined in `backend/app/main.py`; adding an external origin (script/connect/frame) requires updating it. Feed/remote text is rendered as plain text.
6. **i18n.** UI strings are written in French and wrapped in `t('…')` (`useT()` in components, `t` from `i18n` outside). Add the English value to the matching `frontend/src/i18n/en/<area>.js`. Plurals = two keys chosen with `n > 1`. Labels passed to `<Tabs>` are translated by Tabs. Backend user-facing messages are French and translated client-side (add them to `en/*.js` too). Check: no missing key, no conflicting values across dictionaries.
7. **Migrations** are automatic at startup (`init_db`): new columns need a scalar `default=` (becomes SQL `DEFAULT`); constraint changes use `_REBUILD_FOR_USERS`. Never drop user data. Test migrations against a copy of an old DB.
8. **Code style.** Comments and docstrings in **French** (existing convention), identifiers in English. Small functions, type hints, no new dependencies without need. Keep files formatted like their neighbours (Python line length ~140; JS 2-space, no semicolons, single quotes).
9. **Tests.** Add/adjust pytest tests for any backend behaviour change, mandatory for auth, permissions, isolation, migrations, SSRF. Use the fixtures in `backend/tests/conftest.py` and helpers in `tests/test_accounts.py` (`client`, `setup_admin`, `add_member`, `login`).
10. **Versions.** Single source: `backend/app/__init__.py` `__version__` and `frontend/package.json` `version` — bump both together. Release = tag `vX.Y.Z` (builds the multi-arch image to ghcr.io).
11. **Privacy.** Never commit personal data: real host names, IPs, emails, tokens, family names, private URLs, `.env`, databases. Demo data only in screenshots/tests (neutral first names).
12. **Be a good API citizen.** Honest User-Agent, respect rate limits, no bot-detection evasion, no scraping behind logins. JustWatch and AlloCiné/Webedia are unofficial sources: keep them optional and resilient (failures must not break pages).

## Where things are (short)
`backend/app/main.py` app + middlewares + SPA route · `database.py` engine, `UserScoped`, migrations · `config.py` env vars · `scheduler.py` periodic jobs · `models/` · `schemas/` · `routers/<area>.py` · `services/` (clients, sync, history, auth, context, news, health, cache).
`frontend/src/App.jsx` auth gate + routes · `pages/` · `components/{layout,media,admin,profile,ui,…}` · `hooks/useMedia.js` (queries/mutations) · `hooks/useAuth.js` · `services/*.js` (API calls) · `i18n/` · `lib/` (format, appLinks, project) · `store/` (Zustand).
Full map: `docs/ai/map.md`.

## Definition of done
Backend tests green · `vite build` OK · no missing/conflicting translation keys · security rules above respected · docs updated if behaviour or settings changed (`README.md`/`README.en.md`, `docs/`, `.env.example`).
