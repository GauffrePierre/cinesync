"""Jellyfin / Emby : normalisation des titres, liens, connexion du serveur, compte relié, cloisonnement."""

from app.services.jellyfin_client import JellyfinClient
from tests.test_accounts import client, fresh, member, setup_admin  # noqa: F401 (fixture)

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
    # Le membre relie son compte (mot de passe vérifié par le serveur) et retrouve la bibliothèque
    assert alice.post("/api/jellyfin/link", json={"username": "alex", "password": "faux"}).status_code == 403
    assert alice.post("/api/jellyfin/link", json={"username": "alex", "password": "bon-mot-de-passe"}).status_code == 200
    assert alice.get("/api/settings/status").json()["jellyfin"]["linked"] is True
    lib = alice.get("/api/plex/library").json()
    assert lib["results"][0]["server"] == "jellyfin" and lib["results"][0]["id"] == 1433
    # Relié au serveur : il peut demander l'ajout d'un titre, et voit la bibliothèque dans ses statistiques
    assert alice.get("/api/requests").json()["allowed"] is True
    assert alice.get("/api/stats").json()["plex"] == {"movies": 0, "shows": 1, "server": "jellyfin", "watched_movies": 0}
    # Un compte Jellyfin ne peut être relié qu'à un seul compte SynCiné
    assert admin.post("/api/jellyfin/link", json={"username": "alex", "password": "bon-mot-de-passe"}).status_code == 409
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
    async def public_info(self):
        return {"id": "srv1", "name": "Salon", "version": "12.4.0", "kind": "jellyfin"}

    async def users(self):
        return [{"id": "jf-alex", "name": "alex", "admin": False, "disabled": False}, {"id": "jf-sam", "name": "sam", "admin": False, "disabled": False}]

    async def authenticate(self, username, password):
        from app.services.errors import ServiceError

        if password != "bon":
            raise ServiceError("jellyfin", "refusé", 401)
        return {"user_id": f"jf-{username}", "name": username, "token": f"jeton-{username}"}

    monkeypatch.setattr(JellyfinClient, "public_info", public_info)
    monkeypatch.setattr(JellyfinClient, "users", users)
    monkeypatch.setattr(JellyfinClient, "authenticate", authenticate)
    admin = client()
    setup_admin(admin)
    assert client().get("/api/auth/me").json()["jellyfin_login"] is False
    assert client().post("/api/auth/jellyfin", json={"username": "alex", "password": "bon"}).status_code == 404
    admin.post("/api/jellyfin/server", json={"url": "http://jf.test:8096", "api_key": "cle"})
    assert client().get("/api/auth/me").json()["jellyfin_login"] is True
    # Pas encore autorisé par l'admin : refusé, même avec le bon mot de passe
    assert client().post("/api/auth/jellyfin", json={"username": "alex", "password": "bon"}).status_code == 403
    r = admin.post("/api/admin/jellyfin/accounts", json={"jellyfin_user_id": "jf-alex", "display_name": "Alex"})
    assert r.status_code == 200 and r.json()["name"] == "Alex"
    assert admin.post("/api/admin/jellyfin/accounts", json={"jellyfin_user_id": "inconnu"}).status_code == 404
    c = client()
    assert c.post("/api/auth/jellyfin", json={"username": "alex", "password": "faux"}).status_code == 401
    r = c.post("/api/auth/jellyfin", json={"username": "alex", "password": "bon"})
    assert r.status_code == 200 and r.json()["user"]["name"] == "Alex"
    assert c.get("/api/settings/status").json()["jellyfin"]["linked"] is True
    assert {u["name"]: u["jellyfin"] for u in admin.get("/api/admin/users").json()["results"]}["Alex"] == "alex"


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

    async def played_since(self, user_id, since):
        now = datetime.utcnow()
        return [{"kind": "movie", "title": "Film", "watched_at": now - timedelta(days=1), "runtime_min": 120},
                {"kind": "episode", "title": "Série", "watched_at": now - timedelta(days=2), "runtime_min": 60}]

    for name, fn in (("public_info", public_info), ("users", users), ("system_info", system_info), ("sessions", sessions),
                     ("virtual_folders", virtual_folders), ("count", count), ("running_tasks", running_tasks), ("refresh", refresh),
                     ("played_since", played_since)):
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
