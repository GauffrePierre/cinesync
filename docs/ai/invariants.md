# Invariants (AI reference) — things that must stay true

Each item: rule → where enforced → test that guards it (`backend/tests/…`). Breaking one is a bug even if tests pass.

## Accounts & isolation
- A member only ever reads/writes their own personal rows → `UserScoped` + `_scope_to_user` (`database.py`) → `test_accounts.py::test_rows_are_scoped_to_the_bound_user`, `test_members_do_not_see_each_other`.
- Creating a personal row without a bound user raises → `_assign_user` → `test_unbound_session_cannot_create_personal_rows`.
- `all_users=True` appears only in admin/global code: `routers/admin.py`, `routers/requests.py` (`find_open`, admin scope, `_get` for admins), `services/health.py`, `services/history.py` (Plex server import, `assign_plex_events`). Other members' requests are exposed only through `visible()` (status only) → `test_other_members_request_details_stay_private`.
- Server-wide settings writable by admins only → `ADMIN_FIELDS` (`routers/user.py`) → `test_members_cannot_touch_server_settings_or_admin`.
- Members never see server URLs or secret previews → `SettingsOut.from_model(admin=False)` → `test_member_sees_no_server_addresses`.
- At least one active admin; user 1 (holder of server settings) can't be demoted or deleted → `routers/admin.py` → `test_last_admin_is_protected`.
- A temporary password blocks everything except `/auth/*` until changed → `require_ready` → `test_temporary_password_must_be_changed_first`.
- A temporary password stops working 7 days after the admin set it (`User.temp_password_until`, checked at sign-in after the password itself; cleared when the user chooses a password) → `routers/auth.py:login`, `auth.temp_password_deadline` → `test_security_regressions.py::test_temporary_password_expires`.
- Plex sign-in only for Plex accounts linked to an active user that still has access to the admin's server; PIN bound to the browser (nonce cookie) → `routers/auth_external.py`.
- The server Plex connection accepts only a PIN created by the same admin, via POST → `routers/plex.py:_server_pins` → `test_server_plex_pin_must_be_created_by_this_admin`.
- A member without their own Plex token gets **no** Plex access: `ctx.plex` is `None` (no admin-token fallback), `plex_or_mock` raises instead of serving demo data, the status hides the server name, and requests are refused (`can_request`) → `services/context.py`, `routers/requests.py` → `test_member_without_plex_sees_nothing_of_the_admin_plex`.
- Members can't bypass the request queue (no direct Seerr endpoint; `can_send_direct`) → `test_members_cannot_bypass_the_request_queue`.
- Admins see another account's watchlist only if that account turned on `share_watchlist`, and only titles it cannot watch, without its personal state (`routers/admin.py:family_watchlists`, the only `all_users` read of `MediaState` outside sync/admin cleanup) → `test_admin_sees_only_shared_watchlists`.
- Family suggestions read another account only when both accounts turned on `share_taste` (`services/family.py:partners`); only titles flow back, never ratings, history or settings → `test_family_sharing_is_mutual_and_private`.
- From a partner account, family suggestions read only explicit likes (`signals()` entries flagged `loved`: favourite, rating ≥ 8, swipe like, “more like this”) — never watch history, watched-only titles or the watchlist as seeds, since the seed title is returned in the reason (`seeds(..., loved_only=True)`, `family._loved`) → `test_security_regressions.py::test_together_reads_only_what_a_partner_loved`.
- Deleting an account deletes its rows in every `UserScoped` table (`UserScoped.__subclasses__()`, so new tables are covered): SQLite reuses the id for the next account, which must inherit nothing → `routers/admin.py:delete_user` → `test_deleted_account_leaves_nothing_for_the_next_one`.
- Closing an account's sessions (`auth.close_all_sessions`: password change, deactivation, 2FA enabled) also deletes its push subscriptions; the device that stays signed in re-subscribes on next open (`frontend/src/services/push.js:resyncDevice`) → `test_revoked_sessions_lose_their_push_devices`.
- What a member sends in a request is shown to admins: poster must be a TMDB image URL (else dropped), title/note/seasons are length-bounded, at most `MAX_PENDING` pending requests per member → `routers/requests.py:RequestIn` → `test_request_content_comes_from_a_bounded_form`.
- A member cannot flush the shared cache (server fields sent empty are ignored) nor read or test Seerr's state without access to the media server → `routers/user.py` → `test_member_cannot_flush_the_shared_cache_nor_read_seerr_state`.
- Linking a Jellyfin account never grants sign-in: `/auth/jellyfin` needs `User.jellyfin_login` (admin only), contacts the server only for such an allowed account, refuses empty passwords and caps failures per Jellyfin username at 2 per 24 h (`jellyfin_limiter`); linking needs `confirm_identity`; when Quick Connect is enabled the password endpoints are refused (409) and the QC secret never leaves the server (`services/quick_connect.py`) → `routers/auth_external.py:login_jellyfin`, `routers/jellyfin.py:link_account` → `test_sign_in_with_an_authorized_jellyfin_account`, `test_admin_connects_the_server_and_members_link_their_account`, `test_quick_connect_sign_in_and_link`.
- Wrong Jellyfin / Emby passwords forwarded to the server are capped per Jellyfin username at 2 until a success or an admin re-authorisation (`jf:`, never expires: the server only resets its own lockout counter on success); the account's known device keeps its own tries (`jfd:`, 2 per 24 h) so nobody can lock the owner out → `services/auth.py:jellyfin_guard`, `jellyfin_release` → `test_jellyfin.py::test_sign_in_with_an_authorized_jellyfin_account`.
- Other admins are full admins (media server with the server's credentials: token fallback in `Ctx.plex` / `Ctx.jellyfin`, dashboards, `/admin/servers`; server settings and their previews; Plex / Jellyfin server connection; backups) only while the main admin leaves `admins_full_access` on (global setting, writable by user 1 only); off ⇒ they manage accounts and requests only (`Ctx.server_admin`, `require_server_admin`) → `test_security_regressions.py::test_main_admin_chooses_whether_other_admins_see_the_media_server`.
- Another admin can never take over the main admin (user 1): no password reset, 2FA reset or Jellyfin sign-in change on it, and the server owner's Plex account can only be attached to user 1 → `routers/admin.py:update_user`, `allow_plex_account` → `test_security_regressions.py::test_other_admins_cannot_take_over_the_main_admin`. Server-wide watch statistics (`/admin/plex/stats`) need a full admin.

## Editions
- `personal`: user 1 is the only user; no setup, no family accounts, no Plex sign-in; open access until a password is set, then normal sessions → `services/auth.py:session_user`, `require_server_mode` → `test_personal_mode_needs_no_login`, `test_personal_mode_can_be_protected_by_a_password`.
- `personal` with open access: the first password needs the one-time code written to the server logs (`POST /auth/protect/code`, `auth.new_protect_code` / `use_protect_code`, 30 min), so a visitor cannot set it and lock the owner out; removing the password later still returns to open access → `routers/auth.py:change_password` → `test_personal_mode_can_be_protected_by_a_password`.
- Rate-limit subjects are prefixed (`login:`, `2fa:`, `setup`); the signed `cinesync_device` cookie only exempts from `ip:`/`all:` caps → `services/auth.py:guard_attempts`, `known_device` → `test_known_device_still_signs_in_during_a_distributed_attack`, `test_invented_username_cannot_lock_another_counter`.
- The `cinesync_device` cookie carries its signed issue date and is refused after `DEVICE_DAYS` → `auth.known_device` → `test_device_cookie_is_dated`. 2FA recovery codes are stored as HMACs keyed with the server secret (`k1:` prefix; older bare SHA-256 hashes still accepted) → `totp.hash_recovery` → `test_recovery_codes_are_keyed_and_old_ones_still_work`.
- Members without Plex get no Seerr data; members never get Seerr URLs or the admin Plex server name/machine id → `context.Ctx.seerr`, `routers/requests._for`, `SettingsOut.from_model(has_plex)` → `test_member_sees_no_seerr_address_nor_admin_server`.
- Only user 1 links the Plex server (its plex.tv token is also user 1's personal account) → `routers/plex._main_admin_only`.
- Outbound user URLs: decompression done by `safe_fetch._Body` with a cap on the decoded size; image relay accepts JPEG/PNG/WebP/GIF ≤ 16 Mpx, 2 decodes at a time → `test_gzip_bomb_is_stopped_at_the_decompressed_size`, `test_oversized_or_exotic_images_are_refused`.
- Test fixtures refuse to drop tables outside the temporary test DATA_DIR → `tests/conftest.py:assert_test_database`.
- New notifications must use `messages.fields(template, **params)` (template listed in `TEMPLATES` and in `frontend/src/i18n/en`) → `test_templates_are_translated_in_the_interface_too`.
- Push endpoints are user-supplied URLs: only known push services (https) are accepted, a device belongs to one account at a time, logout unsubscribes the device → `services/push.allowed_endpoint`, `routers/push.subscribe` → `tests/test_push.py`.
- First-run assistant: `UserSettings.onboarding` = "pending" for new installs / new accounts (column default "done" keeps existing accounts out); `AuthedApp` renders `pages/Onboarding.jsx` while pending; `/welcome` reruns it → `test_new_accounts_get_the_first_run_assistant`.
- 2FA: with `totp_secret` set, password or Plex sign-in must open NO session (ticket only); codes single-use (`totp_last_counter`), recovery codes hashed and consumed; secret/codes never returned → `routers/auth.py` → `tests/test_two_factor.py`.
- Removing a password is allowed in personal mode or for Plex-linked accounts only → `routers/auth.py:remove_password` → `test_plex_member_can_also_get_a_password`.

## Web security
- Unsafe methods need a same origin (scheme+host+port) → `main.py:same_origin_only` → `test_csrf_check_compares_scheme_host_and_port`.
- Rate limiting by real client address (`request.client.host`, proxies trusted via `FORWARDED_ALLOW_IPS`), graduated keys → `services/auth.py` → `test_wrong_passwords_are_rate_limited`, `test_attacker_cannot_lock_an_account_from_one_address`.
- Failures from a trusted caller (known device of that account, or an open session confirming its password) are counted only on that account's keys (`pair:`, `user:`), never on `ip:` / `all:`: a signed-in member cannot fill the global cap, and an open session can still change its password while the global cap is reached → `services/auth.py:guard_attempts` → `test_signed_in_member_cannot_fill_the_global_counter`, `test_open_session_keeps_sensitive_changes_during_a_distributed_attack`.
- 2FA attempts are counted before the code is checked (ticket tries under `_tickets_lock`, `totp_failures` incremented by the database), so simultaneous requests gain no extra tries → `routers/auth.py:login_two_factor`, `_check_code` → `test_simultaneous_wrong_codes_are_all_counted`.
- Expired Plex sign-in codes are purged before the pending-codes cap is checked (a full table of expired codes must not block Plex sign-in) → `routers/auth_external.py:plex_pin` → `test_expired_plex_codes_do_not_block_plex_sign_in`.
- Security headers + CSP on every response; HSTS only on the `PUBLIC_URL` host; HTTP→HTTPS redirect on that host → `main.py` → `test_security_headers`, `test_hsts_only_on_the_public_domain`, `test_plain_http_on_public_domain_is_redirected`.
- API docs off unless `API_DOCS=true` → `main.py`.
- User-supplied URLs: public addresses only, every redirect checked → `services/safe_fetch.py` → `test_news.py::test_private_or_odd_addresses_are_refused`.
- Relayed images need a server signature → `services/news.py` → `test_image_relay_only_serves_signed_addresses`.
- Feed content shown as plain text → `news._text` → `test_articles_are_plain_text_with_images`.
- SPA route never serves files outside `static/` → `main.py:frontend`.
- Request bodies over 1 MiB are refused (413) before being buffered, declared or chunked (no endpoint takes file uploads) → `main.py:BodyLimit` → `test_security_regressions.py::test_oversized_request_bodies_are_refused`.
- The Plex image relay only accepts library image paths (`plex_client.IMAGE_PATH`: no `..`, query or full URL), relays image types only and serves them sandboxed, like the Jellyfin relay → `test_plex_image_path_cannot_reach_another_resource`.
- Settings strings and lists are length-bounded; the Letterboxd username (placed in the feed URL) is letters, digits and underscores only → `schemas/settings.py:SettingsUpdate` → `test_settings_and_stats_inputs_are_bounded`.
- Text placed in an outbound URL path is reduced to its alphabet first: cinema city search, theatre id and date (`allocine_client.search`, `showtimes`), Plex section id for a scan → `test_cinema_requests_cannot_be_steered_to_another_address`.

## Sync engine (`services/library_sync.py`)
- A service that fails keeps its local data and is not synced that round → `test_failing_service_keeps_its_data_and_is_not_synced`.
- A massive disappearance on one side is never propagated as removals → `test_massive_disappearance_is_not_propagated`.
- Trakt free-account watchlist limit respected (keep most recent) → `test_trakt_watchlist_limit_keeps_most_recent`.
- `auto_sync=False` ⇒ collect only, write nothing → `test_auto_sync_disabled_writes_nothing`.
- Episodes sent to Trakt carry real dates (Plex history) or `released`; never "now" for bulk marks.
- Writes to Plex watched/ratings use the member's own token (`ctx.plex_own`), never the admin's.

## Data & migrations
- Startup migrations never lose rows; legacy single-user data goes to user 1; other Plex accounts' history waits with `user_id=0` until allowed → `init_db` → `test_single_user_database_is_migrated_to_admin`.
- Tokens, API keys and TOTP secrets are stored encrypted (`EncryptedString` columns, `services/crypto.py`); a new secret column must use that type (startup then encrypts existing plain values), and such a column can never be used in a SQL filter. A database read with another server key yields empty values, not errors (services disconnected, 2FA off) → `test_security_regressions.py::test_tokens_are_encrypted_in_the_database`, `test_plain_tokens_of_an_older_database_are_encrypted_at_startup`, `test_database_restored_without_the_server_key_starts_disconnected`.

## Frontend
- No inline scripts, no `dangerouslySetInnerHTML`; external origins must match the CSP.
- Every visible string goes through `t()` with an English entry; no conflicting values across `en/*.js`.
- Server dates without timezone are UTC (`lib/format.js:relativeTime`).
