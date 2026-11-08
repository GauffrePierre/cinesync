# API endpoints (generated from `backend/app/routers`)

All paths are under `/api`. Every router except `auth` requires a ready session (`require_ready`: signed in, temporary password already changed). The `auth` router is public except where noted. **admin** = `require_admin` (router-wide for `/admin`, per-route elsewhere). Docstrings are in French (code convention).

Regenerate: see `docs/ai/recipes.md` → *Regenerate this file*.

## `admin.py`

| Method | Path | Handler | Access | Notes |
|---|---|---|---|---|
| GET | `/api/admin/users` | `list_users` | admin |  |
| POST | `/api/admin/users` | `create_user` | admin, server edition | Compte local : l'admin choisit identifiant et mot de passe provisoire, changé à la première connexion. |
| PATCH | `/api/admin/users/{user_id}` | `update_user` | admin |  |
| DELETE | `/api/admin/users/{user_id}` | `delete_user` | admin | Supprime le compte et ses données personnelles (son historique Plex reste celui du serveur). |
| GET | `/api/admin/plex/accounts` | `plex_accounts` | admin, server edition | Comptes Plex ayant accès au serveur, et ceux déjà autorisés à se connecter à CinéSync. |
| POST | `/api/admin/plex/accounts` | `allow_plex_account` | admin, server edition | Autorise un compte Plex du serveur à se connecter (crée son compte CinéSync). |
| GET | `/api/admin/plex/dashboard` | `plex_dashboard` | admin | Lectures en cours, bibliothèques (nombre de titres, analyse en cours) et état du serveur. |
| POST | `/api/admin/plex/scan` | `plex_scan` | admin | Lance l'analyse d'une bibliothèque (ou de toutes) pour détecter les nouveaux fichiers. |
| GET | `/api/admin/plex/stats` | `plex_stats` | admin | Visionnages sur le serveur (historique Plex importé) : par compte, par jour, titres les plus vus. |

## `auth.py`

| Method | Path | Handler | Access | Notes |
|---|---|---|---|---|
| GET | `/api/auth/me` | `me` | public |  |
| POST | `/api/auth/setup` | `setup` | public, server edition | Création du compte administrateur, avec le code affiché dans les journaux du conteneur. |
| POST | `/api/auth/login` | `login` | public (no session) |  |
| POST | `/api/auth/logout` | `logout` | public (no session) |  |
| POST | `/api/auth/password` | `change_password` | signed in (`current_user`, allowed with a temporary password) | Nouveau mot de passe. L'actuel est demandé, sauf juste après une connexion avec un mot de passe provisoire. |
| DELETE | `/api/auth/password` | `remove_password` | signed in (`current_user`, allowed with a temporary password) | Supprime le mot de passe. Version personnelle : l'accès redevient libre. Version serveur : seulement pour un compte qui peut encore se connecter avec Plex. |
| PUT | `/api/auth/profile` | `update_profile` | signed in (`current_user`, allowed with a temporary password) |  |
| POST | `/api/auth/plex/pin` | `plex_pin` | public, server edition | Étape 1 : code plex.tv. Le code est lié à ce navigateur (cookie) : personne d'autre ne peut l'utiliser. |
| POST | `/api/auth/plex/pin/{pin_id}` | `plex_check` | public, server edition | Étape 2 (interrogée en boucle) : une fois connecté sur plex.tv, vérifie que ce compte Plex est autorisé. |

## `cinema.py`

| Method | Path | Handler | Access | Notes |
|---|---|---|---|---|
| GET | `/api/cinema/countries` | `countries` | session | Pays couverts par la source de séances. |
| GET | `/api/cinema/search` | `search` | session |  |
| GET | `/api/cinema/showtimes` | `showtimes` | session | Films à l'affiche dans tes cinémas pour une date, avec leurs séances par cinéma. |

## `episodes.py`

| Method | Path | Handler | Access | Notes |
|---|---|---|---|---|
| GET | `/api/episodes/{tmdb_id}` | `show_episodes` | session |  |
| POST | `/api/episodes/mark` | `mark_episodes` | session | Marque des épisodes vus / non vus sur Trakt et sur le serveur Plex (épisodes présents). |

## `justwatch.py`

| Method | Path | Handler | Access | Notes |
|---|---|---|---|---|
| GET | `/api/justwatch/charts` | `charts` | session | Top du jour JustWatch dans ton pays (films ou séries). |
| GET | `/api/justwatch/new` | `new_on_platforms` | session |  |

## `letterboxd.py`

| Method | Path | Handler | Access | Notes |
|---|---|---|---|---|
| GET | `/api/letterboxd/diary` | `diary` | session |  |

## `library.py`

| Method | Path | Handler | Access | Notes |
|---|---|---|---|---|
| GET | `/api/library/keys` | `keys` | session | Vue compacte de tout l'état personnel (pour les boutons et badges des cartes). |
| GET | `/api/library/state/{media_type}/{tmdb_id}` | `state` | session |  |
| GET | `/api/library/watchlist` | `watchlist` | session |  |
| POST | `/api/library/watchlist` | `add_watchlist` | session |  |
| DELETE | `/api/library/watchlist/{media_type}/{tmdb_id}` | `remove_watchlist` | session |  |
| POST | `/api/library/watched` | `mark_watched` | session |  |
| POST | `/api/library/rating` | `rate` | session |  |
| POST | `/api/library/like` | `like` | session |  |
| POST | `/api/library/dislike` | `dislike` | session |  |
| DELETE | `/api/library/dislike/{media_type}/{tmdb_id}` | `undislike` | session |  |
| GET | `/api/library/disliked` | `disliked` | session |  |
| DELETE | `/api/library/watched/{media_type}/{tmdb_id}` | `unwatch` | session |  |
| DELETE | `/api/library/like/{media_type}/{tmdb_id}` | `unlike` | session |  |
| GET | `/api/library/sync` | `sync_status` | session |  |
| POST | `/api/library/sync` | `sync_now` | session | Lance une synchronisation. max_age (s) : ne rien faire si la dernière date de moins de max_age |
| GET | `/api/library/sync/preview` | `sync_preview` | session | Simulation : ce que la synchronisation bidirectionnelle ajouterait / retirerait sur chaque service. |

## `media.py`

| Method | Path | Handler | Access | Notes |
|---|---|---|---|---|
| GET | `/api/media/suggestions` | `get_suggestions` | session |  |
| GET | `/api/media/highlights` | `highlights` | session | Diapositives du carrousel de Découvrir : tendance, cinéma, streaming (Plex + plateformes), pour toi. |
| GET | `/api/media/{media_type}/{tmdb_id}` | `full_detail` | session |  |

## `news.py`

| Method | Path | Handler | Access | Notes |
|---|---|---|---|---|
| GET | `/api/news` | `feed` | session |  |
| GET | `/api/news/image` | `image` | session | Image d'un article, relayée et réduite (adresse signée par le serveur, voir services/news.py). |
| GET | `/api/news/catalog` | `catalog` | session |  |
| PUT | `/api/news/sources` | `set_sources` | session | Liste des sources du compte. Une source personnelle n'est gardée que si elle était déjà connue |
| POST | `/api/news/sources/custom` | `add_custom` | session | Ajoute un site (flux RSS ou page), ou une chaîne YouTube, après vérification. |

## `notifications.py`

| Method | Path | Handler | Access | Notes |
|---|---|---|---|---|
| GET | `/api/notifications` | `list_notifications` | session |  |
| POST | `/api/notifications/read-all` | `read_all` | session |  |
| POST | `/api/notifications/check` | `check_now` | session | Lance immédiatement la vérification pour ce compte (normalement toutes les 24 h). |
| POST | `/api/notifications/{notification_id}/read` | `mark_read` | session |  |
| DELETE | `/api/notifications/{notification_id}` | `remove` | session |  |

## `plex.py`

| Method | Path | Handler | Access | Notes |
|---|---|---|---|---|
| GET | `/api/plex/sections` | `sections` | session |  |
| GET | `/api/plex/library` | `library` | session |  |
| GET | `/api/plex/sections/{section_id}/items` | `section_items` | session |  |
| GET | `/api/plex/search` | `search` | session |  |
| GET | `/api/plex/status/{media_type}/{tmdb_id}` | `status` | session |  |
| GET | `/api/plex/image` | `image` | session |  |
| POST | `/api/plex/auth/pin` | `auth_pin` | admin | Étape 1 : crée un code. "link" : à saisir sur plex.tv/link. "window" : fenêtre app.plex.tv. |
| POST | `/api/plex/auth/pin/{pin_id}` | `auth_check` | admin | Étape 2 (interrogée en boucle) : une fois connecté, renvoie la liste de tes serveurs. |
| GET | `/api/plex/servers` | `servers` | admin |  |
| POST | `/api/plex/servers/select` | `select_server` | admin |  |
| POST | `/api/plex/auth/logout` | `logout` | admin |  |
| GET | `/api/plex/watch-link/{media_type}/{tmdb_id}` | `watch_link` | session | Lien watch.plex.tv d'un titre (ouvert par l'app Plex sur iPhone / iPad), ou null. |

## `requests.py`

| Method | Path | Handler | Access | Notes |
|---|---|---|---|---|
| GET | `/api/requests` | `list_requests` | session |  |
| POST | `/api/requests` | `create_request` | session |  |
| POST | `/api/requests/{request_id}/send` | `send_to_seerr` | session |  |
| PATCH | `/api/requests/{request_id}` | `update_request` | session |  |
| DELETE | `/api/requests/{request_id}` | `delete_request` | session |  |

## `search.py`

| Method | Path | Handler | Access | Notes |
|---|---|---|---|---|
| GET | `/api/search` | `global_search` | session |  |

## `seerr.py`

| Method | Path | Handler | Access | Notes |
|---|---|---|---|---|
| GET | `/api/seerr/status/{media_type}/{tmdb_id}` | `status` | session |  |

## `swipe.py`

| Method | Path | Handler | Access | Notes |
|---|---|---|---|---|
| GET | `/api/swipe/queue` | `queue` | session |  |
| POST | `/api/swipe` | `swipe` | session |  |
| POST | `/api/swipe/undo` | `undo` | session | Annule le dernier swipe (localement ; retire aussi de la watchlist Trakt si besoin). |
| GET | `/api/swipe/stats` | `stats` | session |  |
| DELETE | `/api/swipe/history` | `reset` | session |  |

## `tmdb.py`

| Method | Path | Handler | Access | Notes |
|---|---|---|---|---|
| GET | `/api/tmdb/trending` | `trending` | session |  |
| GET | `/api/tmdb/search` | `search` | session |  |
| GET | `/api/tmdb/upcoming` | `upcoming` | session | kind : "cinema" (sorties en salles), "streaming" (sorties numériques + séries) ou "all". |
| GET | `/api/tmdb/on_the_air` | `on_the_air` | session |  |
| GET | `/api/tmdb/genres` | `genres` | session |  |
| GET | `/api/tmdb/collection/{collection_id}` | `collection` | session |  |
| GET | `/api/tmdb/tv/{tv_id}/season/{season_number}` | `season` | session |  |
| GET | `/api/tmdb/{media_type}/{tmdb_id}` | `detail` | session | Fiche TMDB seule. La fiche complète agrégée est sur /api/media/{type}/{id}. |
| GET | `/api/tmdb/{media_type}/{tmdb_id}/providers` | `providers` | session |  |
| GET | `/api/tmdb/{media_type}/{tmdb_id}/similar` | `similar` | session |  |

## `tonight.py`

| Method | Path | Handler | Access | Notes |
|---|---|---|---|---|
| GET | `/api/tonight` | `tonight` | session |  |

## `trakt.py`

| Method | Path | Handler | Access | Notes |
|---|---|---|---|---|
| GET | `/api/trakt/oauth/info` | `oauth_info` | session |  |
| POST | `/api/trakt/device/start` | `device_start` | session |  |
| POST | `/api/trakt/device/poll` | `device_poll` | session |  |
| GET | `/api/trakt/oauth/start` | `oauth_start` | session |  |
| GET | `/api/trakt/oauth/callback` | `oauth_callback` | session |  |
| POST | `/api/trakt/disconnect` | `disconnect` | session |  |
| GET | `/api/trakt/watchlist` | `watchlist` | session |  |
| GET | `/api/trakt/history` | `history` | session |  |
| GET | `/api/trakt/ratings` | `ratings` | session |  |
| GET | `/api/trakt/recommendations` | `recommendations` | session |  |

## `user.py`

| Method | Path | Handler | Access | Notes |
|---|---|---|---|---|
| GET | `/api/settings` | `get_settings` | session |  |
| PUT | `/api/settings` | `update_settings` | session |  |
| GET | `/api/settings/status` | `connection_status` | session |  |
| POST | `/api/settings/test/{service}` | `test_connection` | session |  |
| GET | `/api/meta/countries` | `countries` | session |  |
| GET | `/api/meta/providers` | `providers_catalog` | session | Plateformes disponibles dans le pays configuré (films + séries), triées par popularité. |
| GET | `/api/stats/activity` | `stats_activity` | session | Statistiques détaillées. period : day / week / month / year ; offset : fenêtres vers le passé ; |
| GET | `/api/stats/events` | `stats_events` | session |  |
| POST | `/api/stats/import` | `stats_import` | session |  |
| GET | `/api/stats` | `stats` | session |  |

