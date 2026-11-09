"""Client Jellyfin / Emby (même API, à quelques chemins près) : bibliothèque, index par id TMDB, vus, connexion.

Les titres sont normalisés comme ceux de Plex (mêmes clés : rating_key, id TMDB, plex_url = lien de lecture…)
pour que les pages qui affichent « dans ta bibliothèque » fonctionnent avec l'un ou l'autre serveur ; la clé
`server` indique lequel ("jellyfin" ou "emby").
"""

import asyncio
import hashlib
import ipaddress
import re
from datetime import datetime

import httpx

from app.services.cache import MISS, cache
from app.services.errors import ServiceError
from app.services.http import USER_AGENT, http

CLIENT_NAME = "SynCine"
FIELDS = "ProviderIds,DateCreated,PremiereDate,OfficialRating,Genres,Overview,CriticRating,OriginalTitle"
_index_lock = asyncio.Lock()
ITEM_ID = re.compile(r"^[A-Za-z0-9-]{1,64}$")  # identifiant d'élément ou de bibliothèque


def _date(value: str | None) -> str | None:
    return (value or "")[:10] or None


def _iso(value: str | None) -> str | None:
    """Date Jellyfin (ISO 8601, souvent avec 7 décimales et « Z ») ramenée à la seconde, en UTC."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value[:19]).isoformat() + "Z"
    except ValueError:
        return None


class JellyfinClient:
    is_mock = False

    def __init__(self, url: str, token: str, user_id: str = "", server_id: str = "", public_url: str = "", kind: str = "jellyfin"):
        self.url = url.rstrip("/")
        self.token = token.strip()
        self.user_id = user_id
        self.server_id = server_id
        self.public_url = (public_url or url).rstrip("/")
        self.kind = kind if kind in ("jellyfin", "emby") else "jellyfin"
        self._ns = hashlib.sha256(f"{self.token}|{self.user_id}".encode()).hexdigest()[:12]

    # --- Requêtes --------------------------------------------------------------------------

    def _headers(self, token: str | None = None) -> dict:
        tok = self.token if token is None else token
        auth = f'MediaBrowser Client="{CLIENT_NAME}", Device="SynCine", DeviceId="syncine-{self._ns}", Version="1"'
        if tok:
            auth += f', Token="{tok}"'
        # Jellyfin récent : en-tête Authorization ; Emby : X-Emby-Token
        return {"Authorization": auth, "X-Emby-Authorization": auth, **({"X-Emby-Token": tok} if tok else {}),
                "Accept": "application/json", "User-Agent": USER_AGENT}

    async def _req(self, method: str, path: str, ttl: int = 0, token: str | None = None, json: dict | None = None, **params):
        key = ("jellyfin", self.url, self._ns, method, path, tuple(sorted(params.items())))
        if ttl and (hit := cache.get(key)) is not MISS:
            return hit
        try:
            r = await http().request(method, self.url + path, params=params or None, json=json, headers=self._headers(token), timeout=30.0)
        except httpx.HTTPError as e:
            raise ServiceError(self.kind, f"Serveur {self.label} injoignable : {e.__class__.__name__}") from e
        if r.status_code == 401:
            raise ServiceError(self.kind, f"Accès refusé par {self.label} : clé ou identifiants incorrects", 401)
        if r.status_code >= 400:
            raise ServiceError(self.kind, f"Erreur {self.label} ({r.status_code})", 404 if r.status_code == 404 else 502)
        data = r.json() if r.content and "json" in r.headers.get("content-type", "") else {}
        if ttl:
            cache.set(key, data, ttl)
        return data

    @property
    def label(self) -> str:
        return "Emby" if self.kind == "emby" else "Jellyfin"

    # --- Serveur et comptes ---------------------------------------------------------------

    async def public_info(self) -> dict:
        """Nom, identifiant, version et type du serveur (sans authentification)."""
        d = await self._req("GET", "/System/Info/Public", ttl=600, token="")
        kind = "emby" if "emby" in (d.get("ProductName") or "").lower() else "jellyfin"
        return {"id": d.get("Id") or "", "name": d.get("ServerName") or "", "version": d.get("Version") or "", "kind": kind}

    async def users(self) -> list[dict]:
        """Comptes du serveur (clé API administrateur)."""
        data = await self._req("GET", "/Users")
        return [{
            "id": u.get("Id"), "name": u.get("Name") or "",
            "admin": bool((u.get("Policy") or {}).get("IsAdministrator")),
            "disabled": bool((u.get("Policy") or {}).get("IsDisabled")),
        } for u in data or []]

    async def authenticate(self, username: str, password: str) -> dict:
        """Connexion d'un utilisateur : {user_id, name, token}. Erreur 401 si les identifiants sont faux."""
        d = await self._req("POST", "/Users/AuthenticateByName", token="", json={"Username": username, "Pw": password})
        user = d.get("User") or {}
        if not d.get("AccessToken") or not user.get("Id"):
            raise ServiceError(self.kind, f"Connexion {self.label} impossible", 401)
        return {"user_id": user["Id"], "name": user.get("Name") or username, "token": d["AccessToken"]}

    async def test(self) -> dict:
        info = await self.public_info()
        items = await self._req("GET", "/Items", userId=self.user_id or None, Recursive="true", IncludeItemTypes="Movie,Series", Limit=0)
        return {**info, "titles": items.get("TotalRecordCount", 0)}

    # --- Bibliothèque ---------------------------------------------------------------------

    def web_url(self, item_id: str) -> str | None:
        if not item_id:
            return None
        sid = f"&serverId={self.server_id}" if self.server_id else ""
        if self.kind == "emby":
            return f"{self.public_url}/web/index.html#!/item?id={item_id}{sid}"
        return f"{self.public_url}/web/#/details?id={item_id}{sid}"

    def _normalize(self, m: dict) -> dict:
        ud = m.get("UserData") or {}
        tmdb = (m.get("ProviderIds") or {}).get("Tmdb")
        media_type = "movie" if m.get("Type") == "Movie" else "tv"
        played = bool(ud.get("Played")) or (ud.get("PlayCount") or 0) > 0
        ticks = m.get("RunTimeTicks") or 0
        return {
            "rating_key": m.get("Id"),
            "media_type": media_type,
            "id": int(tmdb) if str(tmdb or "").isdigit() else None,
            "title": m.get("Name"),
            "original_title": m.get("OriginalTitle"),
            "year": m.get("ProductionYear"),
            "overview": m.get("Overview") or "",
            "poster": f"/api/jellyfin/image/{m.get('Id')}?w=342" if (m.get("ImageTags") or {}).get("Primary") else None,
            "backdrop": f"/api/jellyfin/image/{m.get('Id')}?w=1280&kind=Backdrop" if m.get("BackdropImageTags") else None,
            "added_at": _iso(m.get("DateCreated")),
            "vote_average": round(float(m.get("CommunityRating") or 0), 1),
            "critic_score": round(float(m["CriticRating"])) if m.get("CriticRating") else None,
            "audience_score": None,
            "release_date": _date(m.get("PremiereDate")),
            "content_rating": m.get("OfficialRating"),
            "duration_min": round(ticks / 600_000_000) if ticks and media_type == "movie" else None,
            "view_count": 1 if played else 0,
            "user_rating": None,
            "last_viewed_at": _iso(ud.get("LastPlayedDate")),
            "episodes": None,
            "viewed_episodes": (1 if played else 0) if media_type == "tv" else None,
            "section": "Films" if media_type == "movie" else "Séries",
            "section_id": media_type,
            "plex_url": self.web_url(m.get("Id")),  # lien de lecture (clé commune avec Plex)
            "in_plex": True,  # « dans la bibliothèque » (clé commune avec Plex)
            "server": self.kind,
            "providers": [],
        }

    async def library(self) -> list[dict]:
        """Tous les films et séries, avec l'état « vu » du compte (cache 10 min)."""
        key = ("jellyfin", "library", self.url, self._ns)
        if (hit := cache.get(key)) is not MISS:
            return hit
        async with _index_lock:
            if (hit := cache.get(key)) is not MISS:
                return hit
            data = await self._req(
                "GET", "/Items", userId=self.user_id or None, Recursive="true", IncludeItemTypes="Movie,Series",
                Fields=FIELDS, EnableUserData="true", EnableImageTypes="Primary,Backdrop",
            )
            items = [self._normalize(m) for m in data.get("Items", []) or []]
            cache.set(key, items, 600)
            return items

    async def index(self) -> dict[tuple[str, int], dict]:
        return {(i["media_type"], i["id"]): i for i in await self.library() if i["id"]}

    async def sections(self) -> list[dict]:
        return [{"id": "movie", "title": "Films", "type": "movie"}, {"id": "tv", "title": "Séries", "type": "tv"}]

    async def search(self, query: str, limit: int = 20) -> list[dict]:
        q = query.lower().strip()
        return [i for i in await self.library() if q in (i.get("title") or "").lower()][:limit]

    async def image(self, item_id: str, width: int, kind: str = "Primary") -> tuple[bytes, str]:
        try:
            r = await http().get(f"{self.url}/Items/{item_id}/Images/{kind}", params={"maxWidth": width, "quality": 85},
                                 headers=self._headers(), timeout=20.0)
        except httpx.HTTPError as e:
            raise ServiceError(self.kind, f"Image {self.label} indisponible : {e.__class__.__name__}") from e
        if r.status_code >= 400:
            raise ServiceError(self.kind, f"Image {self.label} introuvable", 404)
        return r.content, r.headers.get("content-type", "image/jpeg")

    # --- Vus --------------------------------------------------------------------------------

    async def played_keys(self) -> dict[tuple[str, int], str | None]:
        """Films et séries vus par le compte : {(type, id TMDB): date du dernier visionnage}."""
        return {(i["media_type"], i["id"]): i["last_viewed_at"] for i in await self.library() if i["id"] and i["view_count"]}

    async def set_played(self, item_id: str, played: bool) -> None:
        if not self.user_id:
            raise ServiceError(self.kind, f"Compte {self.label} non relié")
        await self._req("POST" if played else "DELETE", f"/Users/{self.user_id}/PlayedItems/{item_id}")
        cache.clear("jellyfin")

    # --- Lectures en cours (administration) ------------------------------------------------

    async def sessions(self) -> list[dict]:
        data = await self._req("GET", "/Sessions", ActiveWithinSeconds=960)
        return [s for s in data or [] if s.get("NowPlayingItem")]

    async def system_info(self) -> dict:
        """Nom, version et système du serveur (clé API)."""
        return await self._req("GET", "/System/Info")

    async def virtual_folders(self) -> list[dict]:
        """Bibliothèques du serveur (Emby récent renvoie une liste paginée)."""
        data = await self._req("GET", "/Library/VirtualFolders")
        return (data.get("Items") or []) if isinstance(data, dict) else (data or [])

    async def count(self, folder: dict) -> int | None:
        """Nombre de titres d'une bibliothèque (films, séries, albums ou vidéos selon son type)."""
        types = LIBRARY_ITEMS.get(folder.get("CollectionType") or "", "Movie,Series,Video,MusicAlbum")
        data = await self._req("GET", "/Items", ttl=60, ParentId=folder_id(folder), Recursive="true", IncludeItemTypes=types, Limit=0)
        return data.get("TotalRecordCount")

    async def running_tasks(self) -> list[dict]:
        """Tâches planifiées en cours (analyse des bibliothèques, images, sous-titres…)."""
        data = await self._req("GET", "/ScheduledTasks", IsHidden="false")
        return [t for t in data or [] if t.get("State") == "Running"]

    async def refresh(self, folder_id: str | None = None) -> None:
        """Analyse une bibliothèque (nouveaux fichiers), ou toutes."""
        if folder_id:
            await self._req("POST", f"/Items/{folder_id}/Refresh", Recursive="true", MetadataRefreshMode="Default", ImageRefreshMode="Default")
        else:
            await self._req("POST", "/Library/Refresh")

    async def played_history(self, since: datetime | None = None, user_id: str | None = None, cap: int = 10_000) -> list[dict]:
        """Films et épisodes vus par un compte, du plus récent au plus ancien, jusqu'à `since` (exclu).
        Jellyfin et Emby ne gardent que la dernière lecture de chaque titre : un titre revu remplace sa date
        précédente (l'import régulier de l'historique conserve les anciennes)."""
        uid = user_id or self.user_id
        out, start = [], 0
        while start < cap:
            data = await self._req(
                "GET", "/Items", userId=uid, Recursive="true", IncludeItemTypes="Movie,Episode", Filters="IsPlayed",
                SortBy="DatePlayed", SortOrder="Descending", Fields="ProviderIds", EnableUserData="true", StartIndex=start, Limit=500,
            )
            items = data.get("Items", []) or []
            stop = False
            for m in items:
                at = _iso((m.get("UserData") or {}).get("LastPlayedDate"))
                when = datetime.fromisoformat(at[:19]) if at else None
                if when is None:
                    continue  # marqué vu sans date
                if since and when <= since:
                    stop = True
                    break
                out.append(played_item(m, when))
            start += len(items)
            if stop or not items or start >= (data.get("TotalRecordCount") or 0):
                break
        return out

    async def _user_get(self, path: str, **params) -> dict:
        """Route propre au compte : /UserItems/… (Jellyfin 10.9+), sinon /Users/{id}/Items/… (Emby, anciens Jellyfin)."""
        try:
            return await self._req("GET", f"/UserItems/{path}", userId=self.user_id, **params)
        except ServiceError as e:
            if e.status != 404:
                raise
        return await self._req("GET", f"/Users/{self.user_id}/Items/{path}", **params)

    async def in_progress(self, limit: int = 20) -> list[dict]:
        """« Reprendre » : films et épisodes commencés (avec la progression), puis l'épisode suivant des séries en cours."""
        if not self.user_id:
            return []
        resume, next_up = await asyncio.gather(
            self._user_get("Resume", Limit=limit, IncludeItemTypes="Movie,Episode", MediaTypes="Video", Fields="ProviderIds", EnableUserData="true"),
            self._req("GET", "/Shows/NextUp", userId=self.user_id, Limit=limit, Fields="ProviderIds", EnableUserData="true"),
            return_exceptions=True,
        )
        out, shows = [], set()
        for data, started in ((resume, True), (next_up, False)):
            if isinstance(data, BaseException):
                continue
            for m in data.get("Items", []) or []:
                item = played_item(m, None)
                if item["kind"] == "episode":
                    if item["series_id"] in shows:
                        continue  # une seule entrée par série : la plus avancée
                    shows.add(item["series_id"])
                ud, ticks = m.get("UserData") or {}, m.get("RunTimeTicks") or 0
                pos = ud.get("PlaybackPositionTicks") or 0
                if started and ticks and pos:
                    item["progress"] = round(pos / ticks * 100)
                    item["remaining_min"] = round((ticks - pos) / 600_000_000)
                out.append(item)
        return out[:limit]


def played_item(m: dict, when: datetime | None) -> dict:
    """Film ou épisode Jellyfin -> forme commune (historique, reprise)."""
    episode = m.get("Type") == "Episode"
    tmdb = (m.get("ProviderIds") or {}).get("Tmdb")
    return {
        "item_id": m.get("Id"),
        "kind": "episode" if episode else "movie",
        "tmdb": int(tmdb) if not episode and str(tmdb or "").isdigit() else None,  # pour un épisode : celui de la série, via la bibliothèque
        "series_id": m.get("SeriesId") if episode else None,
        "title": m.get("Name") or "",
        "show_title": (m.get("SeriesName") or "") if episode else "",
        "season": m.get("ParentIndexNumber") if episode else None,
        "episode": m.get("IndexNumber") if episode else None,
        "watched_at": when,
        "runtime_min": round((m.get("RunTimeTicks") or 0) / 600_000_000) or None,
    }


# --- Lectures en cours : même forme que celles de Plex (tableau de bord admin) ----------------

LIBRARY_ITEMS = {"movies": "Movie", "tvshows": "Series", "music": "MusicAlbum", "homevideos": "Video,Photo", "musicvideos": "MusicVideo"}
LIBRARY_TYPES = {"movies": "movie", "tvshows": "show", "music": "artist"}


def folder_id(folder: dict) -> str:
    return str(folder.get("ItemId") or folder.get("Id") or "")


def _mbps(bps) -> float | None:
    try:
        return round(float(bps) / 1_000_000, 1) if bps else None
    except (TypeError, ValueError):
        return None


def _is_local(address: str | None) -> bool:
    try:
        ip = ipaddress.ip_address((address or "").strip("[]"))
    except ValueError:
        return False
    ip = getattr(ip, "ipv4_mapped", None) or ip
    return ip.is_private or ip.is_loopback or ip.is_link_local


def _quality(video: dict) -> str | None:
    width = video.get("Width") or 0
    if not width:
        return None
    return "4K" if width >= 3200 else "1080p" if width >= 1800 else "720p" if width >= 1200 else "SD"


def session_summary(s: dict) -> dict:
    """Session Jellyfin / Emby -> lecture en cours (mêmes clés que le tableau de bord Plex)."""
    item, play, tc = s.get("NowPlayingItem") or {}, s.get("PlayState") or {}, s.get("TranscodingInfo") or {}
    kind = {"Episode": "episode", "Movie": "movie"}.get(item.get("Type"), (item.get("Type") or "").lower())
    episode = kind == "episode"
    detail = f"S{item.get('ParentIndexNumber') or 0:02d}E{item.get('IndexNumber') or 0:02d} · {item.get('Name') or ''}" if episode else str(item.get("ProductionYear") or "")
    video = next((x for x in item.get("MediaStreams") or [] if x.get("Type") == "Video"), {})
    method = play.get("PlayMethod") or "DirectPlay"
    if method == "Transcode":
        v, a = ("copy" if tc.get("IsVideoDirect") else "transcode"), ("copy" if tc.get("IsAudioDirect") else "transcode")
    else:
        v = a = "copy" if method == "DirectStream" else "direct"
    overall = "transcode" if "transcode" in (v, a) else ("copy" if "copy" in (v, a) else "direct")
    duration, offset = item.get("RunTimeTicks") or 0, play.get("PositionTicks") or 0
    source = _mbps(item.get("Bitrate") or video.get("BitRate"))
    thumb = item.get("SeriesId") if episode and item.get("SeriesId") else item.get("Id")
    hw = tc.get("HardwareAccelerationType")
    return {
        "id": s.get("Id"),
        "type": kind,
        "title": (item.get("SeriesName") if episode else item.get("Name")) or "",
        "detail": detail,
        "user": s.get("UserName") or "",
        "user_thumb": None,
        "player": s.get("DeviceName") or "",
        "platform": s.get("Client") or "",
        "state": "paused" if play.get("IsPaused") else "playing",
        "local": _is_local(s.get("RemoteEndPoint")),
        "progress": round(offset / duration * 100) if duration else None,
        "remaining_min": round((duration - offset) / 600_000_000) if duration else None,
        "thumb": f"/api/jellyfin/image/{thumb}?w=200" if thumb else None,
        "bandwidth_mbps": (_mbps(tc.get("Bitrate")) if overall == "transcode" else None) or source,
        "source_mbps": source,
        "quality": _quality(video),
        "transcode": overall,
        "video": v,
        "audio": a,
        "transcoding": {
            "active": overall == "transcode",
            "hardware": bool(hw) and str(hw).lower() != "none",
            "speed": None,
            "throttled": False,
            "video_codec": f"{(video.get('Codec') or '').upper()} → {(tc.get('VideoCodec') or '').upper()}" if v == "transcode" else None,
        } if tc else None,
    }
