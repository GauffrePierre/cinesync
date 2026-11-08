"""Client Seerr (Overseerr/Jellyseerr) : statut d'un titre et création de demandes.

CinéSync ne télécharge rien : il crée une demande que tu valides dans Seerr.
"""

import httpx

from app.services.cache import MISS, cache
from app.services.errors import ServiceError
from app.services.http import http

STATUS = {
    1: ("unknown", "Non demandé"),
    2: ("pending", "Demande en attente"),
    3: ("processing", "En cours"),
    4: ("partially_available", "Partiellement disponible"),
    5: ("available", "Disponible"),
    6: ("blacklisted", "Sur liste noire"),
    7: ("deleted", "Supprimé"),
}


class SeerrClient:
    def __init__(self, url: str, api_key: str):
        self.url = url.rstrip("/")
        self.api_key = api_key.strip()

    async def _req(self, method: str, path: str, json: dict | None = None):
        try:
            r = await http().request(
                method,
                f"{self.url}/api/v1{path}",
                json=json,
                headers={"X-Api-Key": self.api_key, "Accept": "application/json"},
            )
        except httpx.HTTPError as e:
            raise ServiceError("seerr", f"Seerr injoignable : {e.__class__.__name__}") from e
        if r.status_code in (401, 403):
            raise ServiceError("seerr", "Clé API Seerr invalide ou droits insuffisants", 401)
        if r.status_code == 404:
            return None
        if r.status_code == 409:
            raise ServiceError("seerr", "Ce titre a déjà été demandé dans Seerr", 409)
        if r.status_code >= 400:
            try:
                msg = r.json().get("message")
            except ValueError:
                msg = None
            raise ServiceError("seerr", f"Erreur Seerr ({r.status_code}){' : ' + msg if msg else ''}")
        return r.json() if r.content else None

    def page_url(self, media_type: str, tmdb_id: int) -> str:
        return f"{self.url}/{media_type}/{tmdb_id}"

    async def media_status(self, media_type: str, tmdb_id: int) -> dict:
        key = ("seerr", media_type, tmdb_id)
        if (hit := cache.get(key)) is not MISS:
            return hit
        data = await self._req("GET", f"/{media_type}/{tmdb_id}") or {}
        info = data.get("mediaInfo") or {}
        code = info.get("status", 1)
        status, label = STATUS.get(code, ("unknown", "Non demandé"))
        out = {
            "status": status,
            "label": label,
            "requested": bool(info.get("requests")) or code in (2, 3),
            "url": self.page_url(media_type, tmdb_id),
        }
        cache.set(key, out, 120)
        return out

    async def request(self, media_type: str, tmdb_id: int, seasons: list[int] | None = None) -> dict:
        body: dict = {"mediaType": media_type, "mediaId": tmdb_id}
        if media_type == "tv":
            body["seasons"] = seasons or "all"
        data = await self._req("POST", "/request", json=body) or {}
        cache.clear("seerr")
        return {"id": data.get("id"), "url": self.page_url(media_type, tmdb_id)}

    async def test(self) -> dict:
        status = await self._req("GET", "/status") or {}
        me = await self._req("GET", "/auth/me") or {}
        return {"version": status.get("version"), "user": me.get("displayName") or me.get("email")}
