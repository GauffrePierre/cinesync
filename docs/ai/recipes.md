# Recipes (AI reference) — step lists for common changes

Always finish with: `cd backend && python -m pytest -q` · `cd frontend && npx vite build` · translation check (below).

## Add a backend endpoint
1. Pick the router in `backend/app/routers/<area>.py` (new file ⇒ `router = APIRouter(prefix="/<area>", tags=["<area>"])`, then add it to the tuple in `main.py` that mounts routers with `Depends(require_ready)`).
2. Signature: `async def name(..., ctx: Ctx = Depends(get_ctx))`. Use `ctx.db` (already bound to the user), `ctx.settings` (`EffectiveSettings`), `ctx.user`, clients `ctx.tmdb/plex/plex_own/trakt/...` (may be `None` when not configured).
3. Admin only ⇒ `dependencies=[Depends(require_admin)]`; server edition only ⇒ `Depends(require_server_mode)`. State changes ⇒ POST/PUT/PATCH/DELETE.
4. Errors: raise `ServiceError(service, "Message en français", status)` / `NotConfigured("service")` / `HTTPException(status, "Message")`. Add the French message + English to `frontend/src/i18n/en/<area>.js`.
5. Pydantic models for bodies with `Field(max_length=…)` limits.
6. Test in `backend/tests/` with `client()`, `setup_admin()`, `add_member()`, `login()` from `test_accounts.py` (fixture `fresh`). Cover member vs admin access if relevant.

## Add a personal table
1. Model in `backend/app/models/<name>.py`: `class X(UserScoped, Base)`; unique constraints must include `"user_id"`. Export in `models/__init__.py`.
2. Created automatically at startup (`create_all`). If an existing table's unique constraint changes ⇒ add it to `_REBUILD_FOR_USERS` in `database.py`.
3. Deleting a user must delete the rows: add the model to the loop in `routers/admin.py:delete_user`.

## Add a setting
1. Column in `models/user_settings.py` with a scalar `default=` (migration adds it with SQL DEFAULT).
2. Server-wide? ⇒ add to `GLOBAL_FIELDS` (`services/context.py`); admin-only writes follow automatically (`ADMIN_FIELDS`). Secret? ⇒ add to `SECRET_FIELDS` (`schemas/settings.py`).
3. Expose in `SettingsOut` / accept in `SettingsUpdate` (`schemas/settings.py`).
4. Frontend: read via `useSettings()`, write via `useUpdateSettings()` (`hooks/useMedia.js`).
5. Env var instead (deployment-level)? ⇒ `config.py` + `.env.example` + README settings table (FR + EN).

## Add an external service client
1. `backend/app/services/<name>_client.py`; use the shared `http()` client (`services/http.py`) for fixed, trusted hosts; `safe_fetch.fetch()` for any user-supplied URL.
2. Cache with `cache.get/set(("<service>", ...), ttl)`; include the user/token in the key if the response is personal.
3. Raise `ServiceError("<service>", msg, status)` on failures; never let an optional service break a page (callers wrap in `safe(...)`).
4. Expose it on `Ctx` as a `cached_property` returning `None` when not configured.
5. Health: add to `services/health.py` (`SERVICES`, `LABELS`, `used_services`, `test_service`; `GLOBAL_SERVICES` if server-wide) and the sidebar `SERVICES` map in `components/layout/Sidebar.jsx`.
6. Update `docs/wiki/08-integrations.md`, README data sources table (FR + EN), credits if required by the provider's terms.

## Add a page (frontend)
1. `frontend/src/pages/<Name>.jsx`; data via a hook in `hooks/useMedia.js` (or a local `useQuery`) calling a wrapper in `services/<area>.js`.
2. Route in `App.jsx` (inside `AuthedApp`), nav entry in `components/layout/nav.js` (`label` French, `short` for the mobile bar, `needs: 'plex'` if it depends on a service).
3. All strings via `const t = useT()` → add English to `i18n/en/<area>.js` (new file ⇒ merge it in `i18n/en/index.js`).
4. Mobile first: check 390 px wide (bottom bar, no horizontal scroll).

## Add or change a translation
- Key = exact French text. Same key must have the same English everywhere. Plurals: two keys. Placeholders `{name}`.
- Check (from the repo root, Node 22): build the frontend, then verify every `t('…')` literal has an English entry and no key has two different values across `frontend/src/i18n/en/*.js` (a small Node script that imports the dictionaries and scans `frontend/src` for `t(` calls does it).

## Release
1. Bump `backend/app/__init__.py` `__version__` and `frontend/package.json` `version`.
2. Update docs/screenshots if UI changed.
3. Tag `vX.Y.Z` on the release commit ⇒ GitHub Actions builds and pushes `ghcr.io/<owner>/cinesync:{X.Y.Z, X.Y, latest}`.

## Regenerate `docs/ai/api.md`
Parse `backend/app/routers/*.py` with `ast`: for each function decorated with `@router.<method>("path")`, output method, `/api` + router prefix + path, handler name, access (admin if `require_admin` on the router or route; `server edition` if `require_server_mode`), and the docstring's first line.
