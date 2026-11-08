"""Client Trakt : OAuth sans secret (code d'appareil ou PKCE) + refresh automatique, watchlist, historique, notes."""

import asyncio
import base64
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
from sqlalchemy.orm import Session

from app import __version__
from app.models import UserSettings
from app.services.cache import MISS, cache
from app.services.errors import NotConfigured, ServiceError
from app.services.http import http

API = "https://api.trakt.tv"
AUTHORIZE_URL = "https://auth.trakt.tv/oauth/authorize"
USER_AGENT = f"SynCine/{__version__}"
OOB_REDIRECT = "urn:ietf:wg:oauth:2.0:oob"

_refresh_lock = asyncio.Lock()


def _key(media_type: str) -> str:
    return "movies" if media_type == "movie" else "shows"


def _mt(trakt_type: str) -> str:
    return "movie" if trakt_type == "movie" else "tv"


def _ref(obj: dict, trakt_type: str) -> dict | None:
    """Objet Trakt (movie/show) -> référence compacte, ou None sans id TMDB."""
    ids = obj.get("ids", {})
    if not ids.get("tmdb"):
        return None
    return {
        "tmdb_id": ids["tmdb"],
        "media_type": _mt(trakt_type),
        "title": obj.get("title"),
        "year": obj.get("year"),
        "trakt_id": ids.get("trakt"),
        "slug": ids.get("slug"),
    }


class TraktClient:
    is_mock = False

    def __init__(self, settings: UserSettings, db: Session):
        self.s = settings
        self.db = db
        # Cache propre au compte SynCiné (chaque membre a son propre Trakt)
        self._ns = getattr(settings, "id", None) or 1

    @property
    def connected(self) -> bool:
        return bool(self.s.trakt_access_token)

    # --- OAuth ---------------------------------------------------------------
    # Deux façons de se connecter, sans client secret (déprécié par Trakt) :
    #  - code d'appareil : l'utilisateur tape un code sur auth.trakt.tv/activate (aucune URL de retour) ;
    #  - PKCE : redirection classique, nécessite une URL de retour HTTPS déclarée dans l'appli Trakt.

    def _client_body(self, **fields) -> dict:
        body = {"client_id": self.s.trakt_client_id, **fields}
        if self.s.trakt_client_secret:  # anciennes applis Trakt uniquement
            body["client_secret"] = self.s.trakt_client_secret
        return body

    async def _post_oauth(self, path: str, body: dict) -> httpx.Response:
        try:
            return await http().post(f"{API}{path}", json=body, headers=self._headers(auth=False))
        except httpx.HTTPError as e:
            raise ServiceError("trakt", f"Trakt injoignable : {e.__class__.__name__}") from e

    # PKCE
    @staticmethod
    def new_pkce() -> tuple[str, str]:
        """(code_verifier, code_challenge S256) — verifier de 64 caractères parmi A-Z a-z 0-9 - . _ ~"""
        verifier = secrets.token_urlsafe(48)[:64]
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        return verifier, challenge

    def authorize_url(self, redirect_uri: str, state: str, code_challenge: str) -> str:
        q = urlencode(
            {
                "response_type": "code",
                "client_id": self.s.trakt_client_id,
                "redirect_uri": redirect_uri,
                "state": state,
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
            }
        )
        return f"{AUTHORIZE_URL}?{q}"

    async def exchange_code(self, code: str, redirect_uri: str, code_verifier: str) -> None:
        body = self._client_body(code=code, redirect_uri=redirect_uri, grant_type="authorization_code", code_verifier=code_verifier)
        await self._store_tokens(await self._post_oauth("/oauth/token", body))
        self.s.trakt_redirect_uri = redirect_uri
        await self._fetch_username()

    # Code d'appareil
    async def device_code(self) -> dict:
        r = await self._post_oauth("/oauth/device/code", {"client_id": self.s.trakt_client_id})
        if r.status_code == 403:
            raise ServiceError("trakt", "Client ID Trakt invalide", 401)
        if r.status_code >= 400:
            raise ServiceError("trakt", f"Trakt a refusé la demande de code ({r.status_code})")
        return r.json()

    async def device_poll(self, device_code: str) -> str:
        """'connected' | 'pending' | 'slow_down' | 'expired' | 'denied' | 'invalid'"""
        r = await self._post_oauth("/oauth/device/token", self._client_body(code=device_code))
        if r.status_code == 200:
            await self._store_tokens(r)
            self.s.trakt_redirect_uri = OOB_REDIRECT
            await self._fetch_username()
            return "connected"
        return {400: "pending", 429: "slow_down", 410: "expired", 418: "denied", 409: "used"}.get(r.status_code, "invalid")

    # Commun
    async def _refresh(self) -> None:
        if not self.s.trakt_refresh_token:
            raise ServiceError("trakt", "Session Trakt expirée — reconnecte-toi dans le Profil", 401)
        body = self._client_body(
            refresh_token=self.s.trakt_refresh_token,
            redirect_uri=self.s.trakt_redirect_uri or OOB_REDIRECT,
            grant_type="refresh_token",
        )
        await self._store_tokens(await self._post_oauth("/oauth/token", body))

    async def _store_tokens(self, r: httpx.Response) -> None:
        if r.status_code >= 400:
            try:
                err = r.json()
                detail = err.get("error_description") or err.get("error") or ""
            except ValueError:
                detail = ""
            raise ServiceError("trakt", f"Échec de l'authentification Trakt ({r.status_code}){' : ' + detail if detail else ''}", 401)
        data = r.json()
        # Les refresh tokens sont à usage unique : on remplace toujours les deux jetons
        self.s.trakt_access_token = data["access_token"]
        self.s.trakt_refresh_token = data.get("refresh_token", "")
        created = datetime.fromtimestamp(data.get("created_at", datetime.now(timezone.utc).timestamp()), timezone.utc)
        self.s.trakt_token_expires_at = (created + timedelta(seconds=data.get("expires_in", 7 * 86400))).replace(tzinfo=None)
        self.s.trakt_code_verifier = ""
        self.s.trakt_oauth_state = ""
        self.db.commit()
        cache.clear("trakt")

    async def _fetch_username(self) -> None:
        try:
            me = await self._request("GET", "/users/settings")
            self.s.trakt_username = me.get("user", {}).get("username", "")
        except ServiceError:
            pass
        self.db.commit()

    async def _ensure_fresh(self) -> None:
        exp = self.s.trakt_token_expires_at
        if exp and datetime.now(timezone.utc).replace(tzinfo=None) > exp - timedelta(hours=12):
            async with _refresh_lock:
                self.db.refresh(self.s)
                exp = self.s.trakt_token_expires_at
                if exp and datetime.now(timezone.utc).replace(tzinfo=None) > exp - timedelta(hours=12):
                    await self._refresh()

    def disconnect(self) -> None:
        self.s.trakt_access_token = ""
        self.s.trakt_refresh_token = ""
        self.s.trakt_token_expires_at = None
        self.s.trakt_username = ""
        self.db.commit()
        cache.clear("trakt")

    # --- Requêtes ------------------------------------------------------------

    def _headers(self, auth: bool) -> dict:
        h = {"Content-Type": "application/json", "trakt-api-version": "2", "trakt-api-key": self.s.trakt_client_id, "User-Agent": USER_AGENT}
        if auth:
            h["Authorization"] = f"Bearer {self.s.trakt_access_token}"
        return h

    async def _request(self, method: str, path: str, *, json=None, params=None, auth: bool = True, ttl: int = 0, _retry: bool = True, meta: dict | None = None):
        if not self.s.trakt_client_id:
            raise NotConfigured("trakt")
        if auth and not self.connected:
            raise NotConfigured("trakt")
        key = ("trakt", self._ns, path, tuple(sorted((params or {}).items())))
        if method == "GET" and ttl and (hit := cache.get(key)) is not MISS:
            return hit
        if auth:
            await self._ensure_fresh()
        try:
            r = await http().request(method, API + path, json=json, params=params, headers=self._headers(auth))
        except httpx.HTTPError as e:
            raise ServiceError("trakt", f"Trakt injoignable : {e.__class__.__name__}") from e

        if r.status_code == 401 and auth and _retry and self.s.trakt_refresh_token:
            async with _refresh_lock:
                await self._refresh()
            return await self._request(method, path, json=json, params=params, auth=auth, ttl=ttl, _retry=False, meta=meta)
        if r.status_code in (401, 403):
            raise ServiceError("trakt", "Session Trakt expirée — reconnecte-toi dans le Profil", 401)
        if r.status_code == 420:
            raise ServiceError("trakt", "Limite du compte Trakt atteinte (la watchlist d'un compte gratuit est plafonnée)", 409)
        if r.status_code == 429:
            raise ServiceError("trakt", "Trop de requêtes Trakt, réessaie dans un instant", 429)
        if r.status_code == 404:
            raise ServiceError("trakt", "Introuvable sur Trakt", 404)
        if r.status_code >= 400:
            raise ServiceError("trakt", f"Erreur Trakt ({r.status_code})")

        data = r.json() if r.content else None
        if meta is not None:  # propre à cet appel (plusieurs lectures tournent en parallèle)
            meta["pages"] = int(r.headers.get("x-pagination-page-count") or 1)
        if method == "GET" and ttl:
            cache.set(key, data, ttl)
        elif method != "GET":
            cache.clear("trakt")
        return data

    async def _get_all(self, path: str, params: dict | None = None, ttl: int = 0) -> list:
        """Toutes les pages d'une liste Trakt.

        Trakt pagine désormais les listes (watchlist, vus, notes…) par 100 éléments par défaut :
        ne lire que la première page faisait croire à des titres « disparus »."""
        key = ("trakt", self._ns, "all", path, tuple(sorted((params or {}).items())))
        if ttl and (hit := cache.get(key)) is not MISS:
            return hit
        out, page = [], 1
        while page <= 200:
            meta: dict = {}
            batch = await self._request("GET", path, params={**(params or {}), "page": page, "limit": 250}, meta=meta) or []
            out += batch
            if page >= meta.get("pages", 1) or not batch:
                break
            page += 1
        if ttl:
            cache.set(key, out, ttl)
        return out

    # --- Lecture -------------------------------------------------------------

    async def watchlist(self) -> list[dict]:
        movies, shows = await asyncio.gather(
            self._get_all("/sync/watchlist/movies", ttl=300),
            self._get_all("/sync/watchlist/shows", ttl=300),
        )
        out = []
        for e in (movies or []) + (shows or []):
            t = e.get("type")
            if (ref := _ref(e.get(t, {}), t)) is not None:
                ref["listed_at"] = e.get("listed_at")
                out.append(ref)
        out.sort(key=lambda x: x.get("listed_at") or "", reverse=True)
        return out

    async def history(self, limit: int = 50) -> list[dict]:
        movies, episodes = await asyncio.gather(
            self._request("GET", "/sync/history/movies", params={"limit": limit}, ttl=300),
            self._request("GET", "/sync/history/episodes", params={"limit": limit * 3}, ttl=300),
        )
        out, seen_shows = [], set()
        for e in movies or []:
            if (ref := _ref(e.get("movie", {}), "movie")) is not None:
                ref["watched_at"] = e.get("watched_at")
                out.append(ref)
        for e in episodes or []:
            ref = _ref(e.get("show", {}), "show")
            if ref is None or ref["tmdb_id"] in seen_shows:
                continue
            seen_shows.add(ref["tmdb_id"])
            ep = e.get("episode", {})
            ref["watched_at"] = e.get("watched_at")
            ref["last_episode"] = f"S{ep.get('season', 0):02d}E{ep.get('number', 0):02d}"
            out.append(ref)
        out.sort(key=lambda x: x.get("watched_at") or "", reverse=True)
        return out

    async def ratings(self) -> list[dict]:
        movies, shows = await asyncio.gather(
            self._get_all("/sync/ratings/movies", ttl=300),
            self._get_all("/sync/ratings/shows", ttl=300),
        )
        out = []
        for e in (movies or []) + (shows or []):
            t = e.get("type")
            if (ref := _ref(e.get(t, {}), t)) is not None:
                ref["rating"] = e.get("rating")  # sur 10
                ref["rated_at"] = e.get("rated_at")
                out.append(ref)
        out.sort(key=lambda x: x.get("rated_at") or "", reverse=True)
        return out

    async def watched_keys(self) -> set[tuple[str, int]]:
        movies, shows = await asyncio.gather(
            self._get_all("/sync/watched/movies", ttl=600),
            self._get_all("/sync/watched/shows", params={"extended": "noseasons"}, ttl=600),
        )
        keys = set()
        for e in movies or []:
            if tid := e.get("movie", {}).get("ids", {}).get("tmdb"):
                keys.add(("movie", tid))
        for e in shows or []:
            if tid := e.get("show", {}).get("ids", {}).get("tmdb"):
                keys.add(("tv", tid))
        return keys

    async def recommendations(self, media_type: str, limit: int = 30) -> list[dict]:
        data = await self._request(
            "GET",
            f"/recommendations/{_key(media_type)}",
            params={"limit": limit, "ignore_collected": "true", "ignore_watchlisted": "true"},
            ttl=3600,
        )
        t = "movie" if media_type == "movie" else "show"
        return [r for e in data or [] if (r := _ref(e, t)) is not None]

    async def stats(self) -> dict:
        return await self._request("GET", "/users/me/stats", ttl=3600) or {}

    async def lookup(self, media_type: str, tmdb_id: int) -> dict | None:
        """Note communautaire Trakt d'un titre à partir de son id TMDB."""
        t = "movie" if media_type == "movie" else "show"
        data = await self._request("GET", f"/search/tmdb/{tmdb_id}", params={"type": t, "extended": "full"}, auth=False, ttl=86400)
        for e in data or []:
            obj = e.get(t)
            if obj:
                slug = obj.get("ids", {}).get("slug")
                return {
                    "rating": round(obj.get("rating") or 0, 1),
                    "votes": obj.get("votes") or 0,
                    "slug": slug,
                    "url": f"https://trakt.tv/{t}s/{slug}" if slug else None,
                }
        return None

    async def me(self) -> dict:
        return await self._request("GET", "/users/settings")

    # --- Écriture ------------------------------------------------------------

    def _body(self, media_type: str, tmdb_id: int, **extra) -> dict:
        return {_key(media_type): [{"ids": {"tmdb": tmdb_id}, **extra}]}

    async def add_to_watchlist(self, media_type: str, tmdb_id: int) -> dict:
        return await self._request("POST", "/sync/watchlist", json=self._body(media_type, tmdb_id))

    async def remove_from_watchlist(self, media_type: str, tmdb_id: int) -> dict:
        return await self._request("POST", "/sync/watchlist/remove", json=self._body(media_type, tmdb_id))

    async def add_to_history(self, media_type: str, tmdb_id: int) -> dict:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        return await self._request("POST", "/sync/history", json=self._body(media_type, tmdb_id, watched_at=now))

    async def remove_from_history(self, media_type: str, tmdb_id: int) -> dict:
        """Retire TOUS les visionnages d'un titre de l'historique Trakt."""
        return await self._request("POST", "/sync/history/remove", json=self._body(media_type, tmdb_id))

    async def remove_from_favorites(self, media_type: str, tmdb_id: int) -> dict:
        return await self._request("POST", "/sync/favorites/remove", json=self._body(media_type, tmdb_id))

    async def hide_recommendation(self, media_type: str, tmdb_id: int) -> dict:
        """« Pas intéressé » : Trakt ne le recommandera plus."""
        return await self._request("POST", "/users/hidden/recommendations", json=self._body(media_type, tmdb_id))

    async def unhide_recommendation(self, media_type: str, tmdb_id: int) -> dict:
        return await self._request("POST", "/users/hidden/recommendations/remove", json=self._body(media_type, tmdb_id))

    async def add_to_favorites(self, media_type: str, tmdb_id: int) -> dict:
        return await self._request("POST", "/sync/favorites", json=self._body(media_type, tmdb_id))

    async def add_many(self, path: str, refs: list[tuple], field: str = "added") -> dict:
        """Envoi groupé par paquets de 100. refs : (media_type, tmdb_id) ou (media_type, tmdb_id, extra)
        où extra est une note ou un dict de champs (watched_at, seasons…).
        path : /sync/watchlist, /sync/watchlist/remove, /sync/history, /sync/ratings."""
        done, not_found = 0, []
        for i in range(0, len(refs), 100):
            body: dict = {"movies": [], "shows": []}
            for ref in refs[i : i + 100]:
                entry = {"ids": {"tmdb": ref[1]}}
                if len(ref) > 2:
                    # 3e élément : une note, ou des champs supplémentaires (ex. watched_at)
                    entry.update(ref[2] if isinstance(ref[2], dict) else {"rating": ref[2]})
                body[_key(ref[0])].append(entry)
            res = await self._request("POST", path, json=body) or {}
            done += sum((res.get(field) or {}).get(k, 0) for k in ("movies", "shows", "episodes"))
            for k, mt in (("movies", "movie"), ("shows", "tv")):
                for nf in (res.get("not_found") or {}).get(k, []) or []:
                    if (nf.get("ids") or {}).get("tmdb"):
                        not_found.append((mt, nf["ids"]["tmdb"]))
        return {field: done, "not_found": not_found}

    async def watchlist_limit(self) -> int | None:
        """Nombre max de titres en watchlist pour ce compte (compte gratuit limité), None si inconnu."""
        try:
            me = await self._request("GET", "/users/settings", ttl=86400)
        except ServiceError:
            return None
        return ((me or {}).get("limits") or {}).get("watchlist", {}).get("item_count")

    async def rate(self, media_type: str, tmdb_id: int, rating10: int) -> dict:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        return await self._request("POST", "/sync/ratings", json=self._body(media_type, tmdb_id, rating=rating10, rated_at=now))
