"""Jellyfin / Emby : normalisation des titres, liens, connexion du serveur, compte relié, cloisonnement."""

import pytest

from app.services.clock import utcnow
from app.services.jellyfin_client import JellyfinClient
from tests.test_accounts import client, fresh, member, setup_admin  # noqa: F401 (fixture)


@pytest.fixture(autouse=True)
def no_quick_connect(monkeypatch):
    """Par défaut, serveur sans Quick Connect (identifiant et mot de passe) ; aucun accès réseau."""
    async def disabled(self):
        return False

    monkeypatch.setattr(JellyfinClient, "quick_connect_enabled", disabled)

ITEM = {
    "Id": "abc123", "Name": "American Dad!", "Type": "Series", "ProductionYear": 2005, "ProviderIds": {"Tmdb": "1433", "Imdb": "tt0397306"},
    "DateCreated": "2026-11-09T09:47:38.7824169Z", "PremiereDate": "2005-02-05T23:00:00.0000000Z", "OfficialRating": "TV-14",
    "CommunityRating": 7.024, "UserData": {"Played": False, "PlayCount": 0}, "ImageTags": {"Primary": "x"}, "BackdropImageTags": ["y"],
}


def test_items_look_like_plex_items():
    c = JellyfinClient("http://jf.test:8096", "k", "u1", "srv", "https://jellyfin.example.org")
    i = c._normalize(ITEM)
    assert (i["media_type"], i["id"], i["year"], i["server"], i["in_plex"]) == ("tv", 1433, 2005, "jellyfin", True)
    assert i["added_at"] == "2026-11-09T09:47:38Z" and i["release_date"] == "2005-02-05"
    assert i["poster"] == "/api/jellyfin/image/abc123?w=342"  # relayée : jamais l'adresse interne
    assert i["plex_url"] == "https://jellyfin.example.org/web/#/details?id=abc123&serverId=srv"
    emby = JellyfinClient("http://emby.test", "k", server_id="s", kind="emby")
    assert emby.web_url("abc") == "http://emby.test/web/index.html#!/item?id=abc&serverId=s"
    movie = c._normalize({**ITEM, "Type": "Movie", "ProviderIds": {}, "RunTimeTicks": 72_000_000_000, "UserData": {"Played": True}})
    assert movie["id"] is None and movie["duration_min"] == 120 and movie["view_count"] == 1


def test_admin_connects_the_server_and_members_link_their_account(fresh, monkeypatch):  # noqa: F811
    async def public_info(self):
        return {"id": "srv1", "name": "Salon", "version": "12.4.0", "kind": "jellyfin"}

    async def users(self):
        return [{"id": "jf-admin", "name": "pierre", "admin": True, "disabled": False}, {"id": "jf-alex", "name": "alex", "admin": False, "disabled": False}]

    async def authenticate(self, username, password):
        from app.services.errors import ServiceError

        if password != "bon-mot-de-passe":
            raise ServiceError("jellyfin", "refusé", 401)
        return {"user_id": f"jf-{username}", "name": username, "token": f"jeton-{username}"}

    async def library(self):
        return [self._normalize(ITEM)]

    monkeypatch.setattr(JellyfinClient, "public_info", public_info)
    monkeypatch.setattr(JellyfinClient, "users", users)
    monkeypatch.setattr(JellyfinClient, "authenticate", authenticate)
    monkeypatch.setattr(JellyfinClient, "library", library)

    admin = client()
    setup_admin(admin)
    alice = member(admin, "alice")
    assert alice.post("/api/jellyfin/server", json={"url": "http://jf.test:8096", "api_key": "cle"}).status_code == 403  # admin seulement
    assert admin.post("/api/jellyfin/server", json={"url": "pas-une-url", "api_key": "cle"}).status_code == 422
    r = admin.post("/api/jellyfin/server", json={"url": "http://jf.test:8096/", "api_key": "cle-secrete"})
    assert r.status_code == 200 and r.json()["server"] == "Salon"
    # La clé n'est jamais renvoyée, l'admin voit la bibliothèque, le membre non relié ne voit rien
    assert "cle-secrete" not in admin.get("/api/settings").text
    st = admin.get("/api/settings/status").json()
    assert st["media"] == {"configured": True, "server": "jellyfin"} and st["jellyfin"]["server"] == "Salon"
    ast = alice.get("/api/settings/status").json()
    assert ast["media"]["configured"] is False and ast["jellyfin"]["server"] is None and ast["jellyfin"]["server_linked"] is True
    assert alice.get("/api/plex/library").status_code == 409
    assert alice.get("/api/requests").json()["allowed"] is False
    # Le membre relie son compte (mot de passe vérifié par le serveur) et retrouve la bibliothèque ;
    # son mot de passe SynCiné est exigé (une session laissée ouverte ne suffit pas)
    assert alice.post("/api/jellyfin/link", json={"username": "alex", "password": "bon-mot-de-passe"}).status_code == 403
    pw = "nouveau-mdp-alice"
    assert alice.post("/api/jellyfin/link", json={"username": "alex", "password": "faux", "current_password": pw}).status_code == 403
    assert alice.post("/api/jellyfin/link", json={"username": "alex", "password": "bon-mot-de-passe", "current_password": pw}).status_code == 200
    assert any("a été relié à ton compte SynCiné" in n["message"] for n in alice.get("/api/notifications").json()["results"])
    # Relier son compte ne permet pas de se connecter à SynCiné avec : seul l'administrateur l'autorise
    assert client().post("/api/auth/jellyfin", json={"username": "alex", "password": "bon-mot-de-passe"}).status_code == 401
    assert alice.get("/api/settings/status").json()["jellyfin"]["linked"] is True
    lib = alice.get("/api/plex/library").json()
    assert lib["results"][0]["server"] == "jellyfin" and lib["results"][0]["id"] == 1433
    # Relié au serveur : il peut demander l'ajout d'un titre, et voit la bibliothèque dans ses statistiques
    assert alice.get("/api/requests").json()["allowed"] is True
    assert alice.get("/api/stats").json()["plex"] == {"movies": 0, "shows": 1, "server": "jellyfin", "watched_movies": 0}
    # Un compte Jellyfin ne peut être relié qu'à un seul compte SynCiné
    assert admin.post("/api/jellyfin/link", json={"username": "alex", "password": "bon-mot-de-passe", "current_password": "motdepasse-admin"}).status_code == 409
    users_list = admin.get("/api/jellyfin/users").json()["results"]
    assert {u["name"]: u["account_name"] for u in users_list} == {"pierre": None, "alex": "Alice"}
    assert alice.request("DELETE", "/api/jellyfin/link").status_code == 200
    assert alice.get("/api/plex/library").status_code == 409


def test_image_relay_rejects_odd_ids(fresh):  # noqa: F811
    admin = client()
    setup_admin(admin)
    assert admin.get("/api/jellyfin/image/..%2F..%2Fetc").status_code == 404
    assert admin.get("/api/jellyfin/image/abc?kind=Logo").status_code == 404


def test_sign_in_with_an_authorized_jellyfin_account(fresh, monkeypatch):  # noqa: F811
    from app.services.errors import ServiceError

    calls = []

    async def public_info(self):
        return {"id": "srv1", "name": "Salon", "version": "12.4.0", "kind": "jellyfin"}

    async def users(self):
        return [{"id": "jf-alex", "name": "alex", "admin": False, "disabled": False}, {"id": "jf-sam", "name": "sam", "admin": False, "disabled": False}]

    async def authenticate(self, username, password):
        calls.append(username.lower())
        if password != "bon":
            raise ServiceError("jellyfin", "refusé", 401)
        name = username.lower()  # comme Jellyfin : identifiant insensible à la casse, compte renvoyé tel qu'enregistré
        return {"user_id": f"jf-{name}", "name": name, "token": f"jeton-{name}"}

    monkeypatch.setattr(JellyfinClient, "public_info", public_info)
    monkeypatch.setattr(JellyfinClient, "users", users)
    monkeypatch.setattr(JellyfinClient, "authenticate", authenticate)
    admin = client()
    setup_admin(admin)
    assert client().get("/api/auth/me").json()["jellyfin_login"] is False
    assert client().post("/api/auth/jellyfin", json={"username": "alex", "password": "bon"}).status_code == 404
    admin.post("/api/jellyfin/server", json={"url": "http://jf.test:8096", "api_key": "cle"})
    assert client().get("/api/auth/me").json()["jellyfin_login"] is False  # aucun compte autorisé : pas de bouton
    # Compte non autorisé : même réponse qu'un mauvais mot de passe, et le serveur Jellyfin n'est pas interrogé
    assert client().post("/api/auth/jellyfin", json={"username": "alex", "password": "bon"}).status_code == 401
    assert client().post("/api/auth/jellyfin", json={"username": "sam", "password": "faux"}).status_code == 401
    assert calls == []
    r = admin.post("/api/admin/jellyfin/accounts", json={"jellyfin_user_id": "jf-alex", "display_name": "Alex"})
    assert r.status_code == 200 and r.json()["name"] == "Alex" and r.json()["jellyfin_login"] is True
    assert admin.post("/api/admin/jellyfin/accounts", json={"jellyfin_user_id": "inconnu"}).status_code == 404
    assert client().get("/api/auth/me").json()["jellyfin_login"] is True
    assert client().post("/api/auth/jellyfin", json={"username": "alex", "password": ""}).status_code == 422  # jamais vide
    c = client()
    assert c.post("/api/auth/jellyfin", json={"username": "alex", "password": "faux"}).status_code == 401
    r = c.post("/api/auth/jellyfin", json={"username": "Alex", "password": "bon"})
    assert r.status_code == 200 and r.json()["user"]["name"] == "Alex"
    assert c.get("/api/settings/status").json()["jellyfin"]["linked"] is True
    assert {u["name"]: u["jellyfin"] for u in admin.get("/api/admin/users").json()["results"]}["Alex"] == "alex"
    # Deux échecs au plus pour un compte visé : SynCiné ne peut pas servir à le bloquer sur le serveur
    for _ in range(2):
        assert client().post("/api/auth/jellyfin", json={"username": "alex", "password": "faux"}).status_code == 401
    assert client().post("/api/auth/jellyfin", json={"username": "alex", "password": "bon"}).status_code == 429
    assert calls.count("alex") == 4
    # Le lendemain, toujours bloqué : le compteur du serveur Jellyfin ne repart qu'après une connexion réussie
    import time

    from app.services import auth as limits

    real = time.monotonic
    monkeypatch.setattr(limits.time, "monotonic", lambda: real() + 25 * 3600)
    assert client().post("/api/auth/jellyfin", json={"username": "alex", "password": "bon"}).status_code == 429
    monkeypatch.setattr(limits.time, "monotonic", real)
    # L'appareil déjà connecté à ce compte garde ses propres essais : personne ne peut enfermer son propriétaire dehors
    c.post("/api/auth/logout")
    assert c.post("/api/auth/jellyfin", json={"username": "alex", "password": "faux"}).status_code == 401
    assert c.post("/api/auth/jellyfin", json={"username": "alex", "password": "bon"}).status_code == 200
    # Sa réussite a remis le compteur à zéro pour tout le monde ; l'administrateur peut aussi lever un blocage
    for _ in range(2):
        assert client().post("/api/auth/jellyfin", json={"username": "alex", "password": "faux"}).status_code == 401
    assert client().post("/api/auth/jellyfin", json={"username": "alex", "password": "bon"}).status_code == 429
    alex = next(u for u in admin.get("/api/admin/users").json()["results"] if u["name"] == "Alex")
    assert admin.patch(f"/api/admin/users/{alex['id']}", json={"jellyfin_login": True}).status_code == 200
    assert client().post("/api/auth/jellyfin", json={"username": "alex", "password": "bon"}).status_code == 200
    # L'administrateur retire l'autorisation : connexion par Jellyfin refusée
    alex_id = r.json()["user"]["id"]
    assert admin.patch(f"/api/admin/users/{alex_id}", json={"jellyfin_login": False}).status_code == 200
    from app.services import auth as auth_service

    auth_service.jellyfin_limiter._fails.clear()
    assert client().post("/api/auth/jellyfin", json={"username": "alex", "password": "bon"}).status_code == 401


def test_server_change_and_unlink_forget_accounts(fresh, monkeypatch):  # noqa: F811
    server = {"id": "srv1"}
    logged_out = []

    async def public_info(self):
        return {"id": server["id"], "name": "Salon", "version": "12.4.0", "kind": "jellyfin"}

    async def users(self):
        return [{"id": "jf-alex", "name": "alex", "admin": False, "disabled": False}]

    async def authenticate(self, username, password):
        return {"user_id": f"jf-{username}", "name": username, "token": f"jeton-{username}"}

    async def logout(self):
        logged_out.append(self.token)

    for name, fn in (("public_info", public_info), ("users", users), ("authenticate", authenticate), ("logout", logout)):
        monkeypatch.setattr(JellyfinClient, name, fn)
    admin = client()
    setup_admin(admin)
    admin.post("/api/jellyfin/server", json={"url": "http://jf.test:8096", "api_key": "cle"})
    alice = member(admin, "alice")
    alice.post("/api/jellyfin/link", json={"username": "alex", "password": "x", "current_password": "nouveau-mdp-alice"})
    assert alice.get("/api/settings/status").json()["jellyfin"]["linked"] is True
    # Délier : jeton révoqué sur le serveur
    assert alice.request("DELETE", "/api/jellyfin/link").status_code == 200
    assert logged_out == ["jeton-alex"]
    alice.post("/api/jellyfin/link", json={"username": "alex", "password": "x", "current_password": "nouveau-mdp-alice"})
    # Un autre serveur : les comptes reliés à l'ancien sont oubliés (leurs jetons n'iraient pas au nouveau)
    server["id"] = "srv2"
    admin.post("/api/jellyfin/server", json={"url": "http://autre.test:8096", "api_key": "cle"})
    assert alice.get("/api/settings/status").json()["jellyfin"]["linked"] is False


def test_device_ids_redirects_and_images(monkeypatch):
    import asyncio

    import httpx

    from app.services import jellyfin_client as jc
    from app.services.errors import ServiceError

    a, b = JellyfinClient("http://jf.test", "", device="alex"), JellyfinClient("http://jf.test", "", device="sam")
    assert a.device_id != b.device_id and a.device_id == JellyfinClient("http://jf.test", "", device="Alex").device_id
    assert "\"" + a.device_id + "\"" in a._headers()["Authorization"]

    def handler(request):
        if request.url.path.endswith("/Primary"):
            return httpx.Response(200, headers={"content-type": "text/html"}, content=b"<script>alert(1)</script>")
        if request.url.path.endswith("/Backdrop"):
            return httpx.Response(200, headers={"content-type": "image/jpeg"}, content=b"x" * (jc.IMAGE_MAX_BYTES + 10))
        return httpx.Response(302, headers={"location": "https://sso.example.org/login"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(jc, "http", lambda: client)
    c = JellyfinClient("http://jf.test", "cle")
    for coro in (c.image("abc", 300, "Primary"), c.image("abc", 300, "Backdrop"), c.users()):
        try:
            asyncio.run(coro)
            raise AssertionError("devait être refusé")
        except ServiceError:
            pass  # page HTML, image trop lourde, redirection : rien n'est relayé ni suivi


class FakeJellyfin:
    user_id = "jf-u1"

    def __init__(self, items):
        self.items = items
        self.played = []

    async def library(self):
        return self.items

    async def index(self):
        return {(i["media_type"], i["id"]): i for i in self.items}

    async def set_played(self, item_id, played):
        self.played.append((item_id, played))


def test_watched_titles_sync_both_ways(db):
    import asyncio

    from app.models import MediaState
    from app.services import library_sync
    from tests.conftest import FakeCtx, lib_item

    jf = FakeJellyfin([lib_item("movie", 603, "jf603", view_count=1, last_viewed_at="2026-11-01T20:00:00Z"), lib_item("movie", 604, "jf604")])
    ctx = FakeCtx(db, auto_sync=False)
    ctx.jellyfin = jf
    asyncio.run(library_sync.pull(ctx))
    row = db.query(MediaState).filter(MediaState.tmdb_id == 603).one()
    assert "jellyfin" in row.sources("watched") and row.watched_at == "2026-11-01T20:00:00Z"
    # Marqué vu dans SynCiné : aussi vu sur Jellyfin (titre de la bibliothèque du compte)
    r = asyncio.run(library_sync.act(ctx, "watched", "movie", 604, title="L604"))
    assert r["services"]["jellyfin"] == "ok" and jf.played == [("jf604", True)]
    asyncio.run(library_sync.act(ctx, "unwatched", "movie", 604))
    assert jf.played[-1] == ("jf604", False)


def test_sessions_look_like_plex_sessions():
    from app.services.jellyfin_client import session_summary

    s = session_summary({
        "Id": "s1", "UserName": "alex", "DeviceName": "Salon", "Client": "Jellyfin Android TV", "RemoteEndPoint": "10.0.0.20",
        "NowPlayingItem": {"Id": "ep1", "SeriesId": "show1", "Type": "Episode", "Name": "Pilote", "SeriesName": "Série", "ParentIndexNumber": 1,
                           "IndexNumber": 2, "RunTimeTicks": 36_000_000_000, "MediaStreams": [{"Type": "Video", "Codec": "hevc", "Width": 3840, "BitRate": 40_000_000}]},
        "PlayState": {"PositionTicks": 9_000_000_000, "IsPaused": False, "PlayMethod": "Transcode"},
        "TranscodingInfo": {"IsVideoDirect": False, "IsAudioDirect": True, "Bitrate": 8_000_000, "VideoCodec": "h264", "HardwareAccelerationType": "vaapi"},
    })
    assert (s["title"], s["detail"], s["user"], s["state"], s["local"]) == ("Série", "S01E02 · Pilote", "alex", "playing", True)
    assert (s["transcode"], s["video"], s["audio"], s["quality"]) == ("transcode", "transcode", "copy", "4K")
    assert (s["progress"], s["remaining_min"], s["bandwidth_mbps"], s["source_mbps"]) == (25, 45, 8.0, 40.0)
    assert s["thumb"] == "/api/jellyfin/image/show1?w=200" and s["transcoding"]["hardware"] and s["transcoding"]["video_codec"] == "HEVC → H264"
    direct = session_summary({"RemoteEndPoint": "8.8.8.8", "NowPlayingItem": {"Type": "Movie", "Name": "Film"}, "PlayState": {"PlayMethod": "DirectPlay", "IsPaused": True}})
    assert (direct["transcode"], direct["local"], direct["state"], direct["transcoding"]) == ("direct", False, "paused", None)


def test_admin_dashboard_and_stats_for_jellyfin(fresh, monkeypatch):  # noqa: F811
    from datetime import datetime, timedelta

    async def public_info(self):
        return {"id": "srv1", "name": "Salon", "version": "10.11.0", "kind": "jellyfin"}

    async def users(self):
        return [{"id": "jf-alex", "name": "alex", "admin": False, "disabled": False}, {"id": "jf-old", "name": "old", "admin": False, "disabled": True}]

    async def system_info(self):
        return {"ServerName": "Salon", "Version": "10.11.0", "OperatingSystemDisplayName": "Linux"}

    async def sessions(self):
        return [{"Id": "s1", "UserName": "alex", "NowPlayingItem": {"Type": "Movie", "Name": "Film", "Id": "m1"}, "PlayState": {"PlayMethod": "DirectPlay"}}]

    async def virtual_folders(self):
        return [{"Name": "Films", "CollectionType": "movies", "ItemId": "f1", "RefreshStatus": "Idle"}]

    async def count(self, folder):
        return 42

    async def running_tasks(self):
        return [{"Name": "Scan Media Library", "Key": "RefreshLibrary", "Category": "Library", "CurrentProgressPercentage": 37.4}]

    refreshed = []

    async def refresh(self, folder_id=None):
        refreshed.append(folder_id)

    async def played_history(self, since=None, user_id=None):
        now = utcnow()
        return [{"kind": "movie", "title": "Film", "show_title": "", "watched_at": now - timedelta(days=1), "runtime_min": 120},
                {"kind": "episode", "title": "Pilote", "show_title": "Série", "watched_at": now - timedelta(days=2), "runtime_min": 60}]

    for name, fn in (("public_info", public_info), ("users", users), ("system_info", system_info), ("sessions", sessions),
                     ("virtual_folders", virtual_folders), ("count", count), ("running_tasks", running_tasks), ("refresh", refresh),
                     ("played_history", played_history)):
        monkeypatch.setattr(JellyfinClient, name, fn)

    admin = client()
    setup_admin(admin)
    alice = member(admin, "alice")
    assert admin.get("/api/admin/servers").json()["results"] == []
    assert admin.get("/api/admin/jellyfin/dashboard").status_code == 409
    admin.post("/api/jellyfin/server", json={"url": "http://jf.test:8096", "api_key": "cle"})
    assert admin.get("/api/admin/servers").json()["results"] == [{"id": "jellyfin", "kind": "jellyfin", "name": "Salon"}]
    for path in ("/api/admin/servers", "/api/admin/jellyfin/dashboard", "/api/admin/jellyfin/stats"):
        assert alice.get(path).status_code == 403
    assert alice.post("/api/admin/jellyfin/scan").status_code == 403
    d = admin.get("/api/admin/jellyfin/dashboard").json()
    assert d["server"] == {"kind": "jellyfin", "name": "Salon", "version": "10.11.0", "platform": "Linux"}
    assert d["totals"]["streams"] == 1 and d["sessions"][0]["title"] == "Film"
    assert d["libraries"] == [{"id": "f1", "title": "Films", "type": "movie", "count": 42, "scanned_at": None, "refreshing": True}]
    assert d["activities"][0]["progress"] == 37
    assert admin.post("/api/admin/jellyfin/scan?section_id=f1").status_code == 200
    assert admin.post("/api/admin/jellyfin/scan").status_code == 200
    assert admin.post("/api/admin/jellyfin/scan?section_id=../x").status_code == 404
    assert refreshed == ["f1", None]
    st = admin.get("/api/admin/jellyfin/stats?days=7").json()
    assert (st["approx"], st["plays"], st["movies"], st["episodes"], st["hours"]) == (True, 2, 1, 1, 3)
    assert st["by_user"] == [{"name": "alex", "plays": 2}] and len(st["by_day"]) == 7


def _played(item_id, kind, at, tmdb=None, series_id=None, season=None, episode=None, title="T"):
    return {"item_id": item_id, "kind": kind, "tmdb": tmdb, "series_id": series_id, "title": title, "show_title": "Série" if series_id else "",
            "season": season, "episode": episode, "watched_at": at, "runtime_min": 50}


def test_jellyfin_history_import(db):
    import asyncio
    from datetime import datetime, timedelta

    from app.models import WatchEvent
    from app.services import history
    from tests.conftest import FakeCtx, lib_item

    now = datetime(2026, 11, 9, 21, 0)
    bulk_at = datetime(2026, 10, 1, 12, 0, 30)

    class Jf(FakeJellyfin):
        def __init__(self, items, played):
            super().__init__(items)
            self.played_list, self.since = played, []

        async def played_history(self, since=None, user_id=None):
            self.since.append(since)
            return [p for p in self.played_list if since is None or p["watched_at"] > since]

    played = [
        _played("jf603", "movie", now - timedelta(days=1)),  # id TMDB via la bibliothèque
        _played("ep1", "episode", now - timedelta(days=2), series_id="show1", season=1, episode=3),
        _played("jf999", "movie", now - timedelta(days=3), tmdb=999),
    ] + [_played(f"b{i}", "movie", bulk_at, tmdb=5000 + i) for i in range(25)]  # marqués vus par lot
    jf = Jf([lib_item("movie", 603, "jf603"), lib_item("tv", 1399, "show1")], played)
    ctx = FakeCtx(db)
    ctx.jellyfin = jf
    # Déjà connu par Trakt à quelques heures près : pas de doublon
    db.add(WatchEvent(source="trakt", source_key="t1", kind="movie", tmdb_id=999, watched_at=now - timedelta(days=3, hours=2)))
    db.commit()
    assert asyncio.run(history.import_jellyfin(ctx)) == 27
    rows = {r.source_key.split(":")[0]: r for r in db.query(WatchEvent).filter(WatchEvent.source == "jellyfin")}
    assert rows["jf603"].tmdb_id == 603 and rows["ep1"].tmdb_id == 1399 and (rows["ep1"].season, rows["ep1"].episode) == (1, 3)
    assert "jf999" not in rows
    assert rows["b0"].approx_date is True and rows["jf603"].approx_date is False
    # Import suivant : seulement les nouvelles lectures (un film revu garde aussi sa lecture précédente)
    jf.played_list.append(_played("jf603", "movie", now + timedelta(hours=1)))
    assert asyncio.run(history.import_jellyfin(ctx)) == 1
    assert jf.since == [None, now - timedelta(days=1, minutes=1)]  # depuis la dernière lecture importée
    assert db.query(WatchEvent).filter(WatchEvent.source == "jellyfin", WatchEvent.tmdb_id == 603).count() == 2
    # Admin sans compte Jellyfin relié (clé API) : rien à importer
    jf.user_id = ""
    assert asyncio.run(history.import_jellyfin(ctx)) == 0


def test_in_progress_reads_resume_and_next_up_with_emby_fallback(monkeypatch):
    import asyncio

    from app.services.errors import ServiceError

    calls = []

    async def fake_req(self, method, path, ttl=0, token=None, json=None, **params):
        calls.append(path)
        if path == "/UserItems/Resume":
            raise ServiceError("emby", "Erreur Emby (404)", 404)  # Emby : ancienne route
        if path == "/Users/u1/Items/Resume":
            return {"Items": [
                {"Id": "m1", "Type": "Movie", "Name": "Film", "ProviderIds": {"Tmdb": "603"}, "RunTimeTicks": 72_000_000_000,
                 "UserData": {"PlaybackPositionTicks": 18_000_000_000}},
                {"Id": "e5", "Type": "Episode", "Name": "Cinq", "SeriesId": "s1", "SeriesName": "Série", "ParentIndexNumber": 2, "IndexNumber": 5,
                 "RunTimeTicks": 30_000_000_000, "UserData": {"PlaybackPositionTicks": 15_000_000_000}},
            ]}
        if path == "/Shows/NextUp":
            return {"Items": [
                {"Id": "e6", "Type": "Episode", "Name": "Six", "SeriesId": "s1", "SeriesName": "Série", "ParentIndexNumber": 2, "IndexNumber": 6},
                {"Id": "x1", "Type": "Episode", "Name": "Un", "SeriesId": "s2", "SeriesName": "Autre", "ParentIndexNumber": 1, "IndexNumber": 1},
            ]}
        raise AssertionError(path)

    monkeypatch.setattr(JellyfinClient, "_req", fake_req)
    c = JellyfinClient("http://emby.test", "tok", "u1", kind="emby")
    items = asyncio.run(c.in_progress())
    assert [i["item_id"] for i in items] == ["m1", "e5", "x1"]  # une seule entrée par série, la plus avancée
    assert (items[0]["tmdb"], items[0]["progress"], items[0]["remaining_min"]) == (603, 25, 90)
    assert (items[1]["series_id"], items[1]["season"], items[1]["episode"], items[1]["progress"]) == ("s1", 2, 5, 50)
    assert "progress" not in items[2]
    assert set(calls) == {"/UserItems/Resume", "/Users/u1/Items/Resume", "/Shows/NextUp"}
    assert asyncio.run(JellyfinClient("http://emby.test", "k", "").in_progress()) == []  # sans compte relié


def test_tonight_resume_row_with_jellyfin():
    import asyncio
    from types import SimpleNamespace

    from app.routers.tonight import _jellyfin_deck

    class Jf:
        kind = "jellyfin"

        async def in_progress(self):
            return [
                {"item_id": "m1", "kind": "movie", "tmdb": 603, "series_id": None, "title": "Matrix", "progress": 25, "remaining_min": 90},
                {"item_id": "e6", "kind": "episode", "tmdb": None, "series_id": "s1", "title": "Six", "season": 2, "episode": 6},
                {"item_id": "x", "kind": "episode", "tmdb": None, "series_id": "inconnue", "title": "?", "season": 1, "episode": 1},
            ]

        def web_url(self, item_id):
            return f"https://jf.example.org/web/#/details?id={item_id}"

    class Tmdb:
        is_mock = False

        async def basic(self, media_type, tmdb_id):
            return {"id": tmdb_id, "media_type": media_type, "title": f"T{tmdb_id}"}

    ctx = SimpleNamespace(jellyfin=Jf(), tmdb=Tmdb())
    index = {("tv", 1399): {"rating_key": "s1", "id": 1399}}
    items = asyncio.run(_jellyfin_deck(ctx, index))
    assert [(i["media_type"], i["id"]) for i in items] == [("movie", 603), ("tv", 1399)]  # série inconnue de la bibliothèque : ignorée
    assert items[0]["progress"] == 25 and items[0]["resume"] == "Reprendre le film" and items[0]["server"] == "jellyfin"
    assert items[1]["resume"] == "S02E06 · Six" and "progress" not in items[1] and items[1]["plex_url"].endswith("id=e6")


def test_quick_connect_sign_in_and_link(fresh, monkeypatch):  # noqa: F811
    """Quick Connect : code validé dans Jellyfin, aucun mot de passe Jellyfin saisi dans SynCiné."""
    approved, revoked = set(), []

    async def public_info(self):
        return {"id": "srv1", "name": "Salon", "version": "10.11.0", "kind": "jellyfin"}

    async def users(self):
        return [{"id": "jf-alex", "name": "alex", "admin": False, "disabled": False}, {"id": "jf-sam", "name": "sam", "admin": False, "disabled": False}]

    async def enabled(self):
        return True

    async def start(self):
        return {"secret": f"secret-{self.device_id}", "code": "123456"}

    async def is_approved(self, secret):
        return secret in approved

    async def qc_auth(self, secret):
        who = approved_by[secret]
        return {"user_id": f"jf-{who}", "name": who, "token": f"jeton-{who}-{len(revoked)}"}

    async def logout(self):
        revoked.append(self.token)

    async def authenticate(self, username, password):
        raise AssertionError("aucun mot de passe Jellyfin ne doit être envoyé")

    approved_by = {}
    for name, fn in (("public_info", public_info), ("users", users), ("quick_connect_enabled", enabled), ("quick_connect_start", start),
                     ("quick_connect_approved", is_approved), ("quick_connect_auth", qc_auth), ("logout", logout), ("authenticate", authenticate)):
        monkeypatch.setattr(JellyfinClient, name, fn)

    def approve(secret_holder, who):
        from app.services import quick_connect

        p = quick_connect._pending[secret_holder]
        approved.add(p.secret)
        approved_by[p.secret] = who

    admin = client()
    setup_admin(admin)
    admin.post("/api/jellyfin/server", json={"url": "http://jf.test:8096", "api_key": "cle"})
    assert client().get("/api/auth/jellyfin/quickconnect").json() == {"enabled": True}
    # Mot de passe refusé : Quick Connect est disponible
    assert client().post("/api/auth/jellyfin", json={"username": "alex", "password": "x"}).status_code == 409
    assert client().post("/api/auth/jellyfin/quickconnect").status_code == 404  # aucun compte autorisé
    admin.post("/api/admin/jellyfin/accounts", json={"jellyfin_user_id": "jf-alex", "display_name": "Alex"})

    # Connexion : code affiché, en attente, puis validé dans Jellyfin
    c = client()
    r = c.post("/api/auth/jellyfin/quickconnect").json()
    assert r["code"] == "123456" and "secret" not in r
    assert c.post(f"/api/auth/jellyfin/quickconnect/{r['id']}").json() == {"status": "pending"}
    approve(r["id"], "alex")
    me = c.post(f"/api/auth/jellyfin/quickconnect/{r['id']}").json()
    assert me["user"]["name"] == "Alex" and c.get("/api/settings/status").json()["jellyfin"]["linked"] is True
    assert c.post(f"/api/auth/jellyfin/quickconnect/{r['id']}").status_code == 410  # usage unique

    # Compte Jellyfin non autorisé : refusé, et le jeton tout juste créé est révoqué
    c2 = client()
    r = c2.post("/api/auth/jellyfin/quickconnect").json()
    approve(r["id"], "sam")
    assert c2.post(f"/api/auth/jellyfin/quickconnect/{r['id']}").status_code == 403
    assert revoked[-1].startswith("jeton-sam") and c2.get("/api/auth/me").json()["user"] is None
    assert client().post("/api/auth/jellyfin/quickconnect/inconnu").status_code == 410

    # Relier son compte : mot de passe SynCiné exigé, demande propre au compte qui l'a lancée
    alice = member(admin, "bob")
    assert alice.post("/api/jellyfin/link", json={"username": "sam", "password": "x", "current_password": "nouveau-mdp-bob"}).status_code == 409
    assert alice.post("/api/jellyfin/link/quickconnect", json={}).status_code == 403
    r = alice.post("/api/jellyfin/link/quickconnect", json={"current_password": "nouveau-mdp-bob"}).json()
    assert admin.post(f"/api/jellyfin/link/quickconnect/{r['id']}").status_code == 410  # la demande d'un autre compte
    assert alice.post(f"/api/jellyfin/link/quickconnect/{r['id']}").json() == {"status": "pending"}
    approve(r["id"], "sam")
    assert alice.post(f"/api/jellyfin/link/quickconnect/{r['id']}").json()["status"] == "linked"
    st = alice.get("/api/settings/status").json()["jellyfin"]
    assert st["linked"] is True and st["username"] == "sam"
    # Relier ne donne pas la connexion par Jellyfin
    assert {u["username"]: u["jellyfin_login"] for u in admin.get("/api/admin/users").json()["results"]}["bob"] is False


def test_request_available_notification_names_the_server(fresh, monkeypatch):  # noqa: F811
    from app.database import SessionLocal
    from app.models import MediaRequest

    async def public_info(self):
        return {"id": "srv1", "name": "Salon", "version": "10.11.0", "kind": "jellyfin"}

    async def users(self):
        return []

    monkeypatch.setattr(JellyfinClient, "public_info", public_info)
    monkeypatch.setattr(JellyfinClient, "users", users)
    admin = client()
    setup_admin(admin)
    admin.post("/api/jellyfin/server", json={"url": "http://jf.test:8096", "api_key": "cle"})
    alice = member(admin, "alice")
    alice_id = alice.get("/api/auth/me").json()["user"]["id"]
    with SessionLocal() as db:
        db.add(MediaRequest(user_id=alice_id, tmdb_id=603, media_type="movie", title="Matrix", status="pending"))
        db.commit()
    req_id = admin.get("/api/requests?scope=all").json()["results"][0]["id"]
    assert admin.patch(f"/api/requests/{req_id}", json={"status": "available"}).status_code == 200
    messages = [n["message"] for n in alice.get("/api/notifications").json()["results"]]
    assert "Ta demande « Matrix » est disponible sur Jellyfin" in messages
