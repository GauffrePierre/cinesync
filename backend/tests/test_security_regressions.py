"""Régressions de sécurité (audit de novembre 2026) : chaque test reproduit une faille corrigée."""

import asyncio
import threading
import time
from datetime import timedelta

from sqlalchemy import select

from app.database import SessionLocal, UserScoped
from app.models import MediaState, Notification, PushSubscription, User, UserSettings, WatchEvent
from app.routers import auth as auth_router
from app.routers import auth_external
from app.services import auth, family, plex_auth, totp
from app.services.cache import MISS, cache
from app.services.clock import utcnow
from tests.test_accounts import add_member, client, fresh, link_plex, login, member, setup_admin  # noqa: F401 (fixture)
from tests.test_family import _ctx, _item, _no_enrich

FCM = "https://fcm.googleapis.com/fcm/send/appareil"
KEYS = {"p256dh": "x" * 20, "auth": "y" * 10}


def _ids(admin) -> dict[str, int]:
    return {u["username"]: u["id"] for u in admin.get("/api/admin/users").json()["results"]}


# --- Isolation ---------------------------------------------------------------------------


def test_deleted_account_leaves_nothing_for_the_next_one(fresh):  # noqa: F811
    """L'id d'un compte supprimé peut être repris par le suivant : aucune ligne personnelle ne doit rester
    (un abonnement push oublié envoyait les notifications du nouveau compte à l'appareil de l'ancien)."""
    admin = client()
    setup_admin(admin)
    bob = member(admin, "bob")
    bob_id = _ids(admin)["bob"]
    assert bob.post("/api/push/subscribe", json={"endpoint": FCM, "keys": KEYS}).status_code == 200
    assert admin.delete(f"/api/admin/users/{bob_id}").status_code == 200
    with SessionLocal() as db:
        for model in UserScoped.__subclasses__():
            left = db.execute(select(model).where(model.user_id == bob_id).execution_options(all_users=True)).scalars().all()
            assert left == [], f"{model.__name__} : lignes restantes après suppression du compte"
    alice = member(admin, "alice")
    assert alice.get("/api/push/config").json()["devices"] == 0


def test_revoked_sessions_lose_their_push_devices(fresh):  # noqa: F811
    """Compte désactivé ou mot de passe changé : les appareils abonnés ne reçoivent plus les notifications."""
    admin = client()
    setup_admin(admin)
    bob = member(admin, "bob")
    bob_id = _ids(admin)["bob"]
    bob.post("/api/push/subscribe", json={"endpoint": FCM, "keys": KEYS})
    assert admin.patch(f"/api/admin/users/{bob_id}", json={"active": False}).status_code == 200
    with SessionLocal() as db:
        assert db.execute(select(PushSubscription).execution_options(all_users=True)).scalars().all() == []
    # Changement de mot de passe par le compte lui-même : pareil (l'appareil courant se réabonne à l'ouverture)
    admin.post("/api/push/subscribe", json={"endpoint": FCM + "2", "keys": KEYS})
    assert admin.post("/api/auth/password", json={"current_password": "motdepasse-admin", "new_password": "motdepasse-admin-2"}).status_code == 200
    with SessionLocal() as db:
        assert db.execute(select(PushSubscription).execution_options(all_users=True)).scalars().all() == []


def test_together_reads_only_what_a_partner_loved(fresh, monkeypatch):  # noqa: F811
    """« À deux » : seuls les coups de cœur et bonnes notes de l'autre compte servent (ce qu'annonce le partage),
    jamais son historique, ses titres seulement vus ni sa watchlist."""
    monkeypatch.setattr(family, "enrich", _no_enrich)
    admin = client()
    setup_admin(admin)
    member(admin, "alice"), member(admin, "bob")
    ids = _ids(admin)
    with SessionLocal() as db:
        db.add_all([
            MediaState(user_id=ids["bob"], tmdb_id=1, media_type="movie", title="Coup de cœur de Bob", liked=True),
            MediaState(user_id=ids["bob"], tmdb_id=2, media_type="movie", title="Vu par Bob", watched_sources='["trakt"]'),
            MediaState(user_id=ids["bob"], tmdb_id=3, media_type="movie", title="Watchlist de Bob", watchlist_sources='["local"]'),
            MediaState(user_id=ids["bob"], tmdb_id=5, media_type="movie", title="Mal noté par Bob", rating=3, watched_sources='["trakt"]'),
            WatchEvent(user_id=ids["bob"], source="plex", source_key="k1", kind="movie", tmdb_id=4, title="Regardé par Bob", watched_at=utcnow() - timedelta(days=2)),
        ])
        db.commit()
    names = {1: "Alpha", 2: "Bravo", 3: "Charlie", 4: "Delta", 5: "Echo"}  # une recommandation par titre de Bob
    recs = {("movie", n): [_item(100 + n, name)] for n, name in names.items()}
    with SessionLocal() as db:
        out = asyncio.run(family.together(_ctx(db, ids["alice"], recs), [(ids["bob"], "Bob")], "movie"))
    assert [i["title"] for i in out] == ["Alpha"]
    assert out[0]["reason_params"] == {"name": "Bob", "title": "Coup de cœur de Bob"}


def test_request_content_comes_from_a_bounded_form(fresh):  # noqa: F811
    """Demande d'ajout : affiche TMDB seulement (l'admin ne charge pas une adresse choisie par un membre),
    titre et note de longueur bornée, nombre de demandes en attente plafonné par membre."""
    admin = client()
    setup_admin(admin)
    alice = member(admin, "alice")
    link_plex(_ids(admin)["alice"])
    r = alice.post("/api/requests", json={"tmdb_id": 1, "media_type": "movie", "title": "A", "poster": "https://attaquant.example/p.png"})
    assert r.status_code == 200 and r.json()["request"]["poster"] is None
    ok = "https://image.tmdb.org/t/p/w342/abc.jpg"
    assert alice.post("/api/requests", json={"tmdb_id": 2, "media_type": "movie", "title": "B", "poster": ok}).json()["request"]["poster"] == ok
    odd = ("https://image.tmdb.org.attaquant.example/t/p/w342/a.jpg", "https://image.tmdb.org/t/p/../../x", "http://image.tmdb.org/t/p/w342/a.jpg")
    for n, poster in enumerate(odd, start=5):
        assert alice.post("/api/requests", json={"tmdb_id": n, "media_type": "movie", "poster": poster}).json()["request"]["poster"] is None
    assert alice.post("/api/requests", json={"tmdb_id": 4, "media_type": "movie", "title": "x" * 301}).status_code == 422
    assert alice.post("/api/requests", json={"tmdb_id": 4, "media_type": "movie", "note": "x" * 501}).status_code == 422
    assert alice.post("/api/requests", json={"tmdb_id": 4, "media_type": "movie", "seasons": list(range(200))}).status_code == 422
    for n in range(10, 10 + 50):
        last = alice.post("/api/requests", json={"tmdb_id": n, "media_type": "movie", "title": f"T{n}"})
    assert last.status_code == 429
    assert len(alice.get("/api/requests").json()["results"]) == 50


def test_member_cannot_flush_the_shared_cache_nor_read_seerr_state(fresh):  # noqa: F811
    admin = client()
    setup_admin(admin)
    assert admin.put("/api/settings", json={"seerr_url": "http://seerr.test", "seerr_api_key": "cle"}).status_code == 200
    alice = member(admin, "alice")
    cache.set(("tmdb", "temoin"), 1, 600)
    # Champ du serveur envoyé vide par un membre : ignoré, et le cache commun reste en place
    assert alice.put("/api/settings", json={"tmdb_api_key": None, "country_code": "be"}).status_code == 200
    assert cache.get(("tmdb", "temoin")) is not MISS
    # Membre non relié au serveur multimédia : ni l'état de Seerr, ni le droit de le faire tester
    assert "seerr" not in alice.get("/api/settings/status").json()["health"]
    assert alice.post("/api/settings/test/seerr").status_code == 403
    assert "seerr" in admin.get("/api/settings/status").json()["health"]


# --- Authentification ----------------------------------------------------------------------


def test_expired_plex_codes_do_not_block_plex_sign_in(fresh, monkeypatch):  # noqa: F811
    """La table des codes en attente pleine de codes expirés : ils sont purgés, la connexion Plex reste possible."""
    admin = client()
    setup_admin(admin)
    with SessionLocal() as db:
        s = db.get(UserSettings, 1)
        s.plex_machine_id, s.plex_client_id = "machine", "client"
        db.commit()

    async def create_pin(client_id, mode, forward=None):
        return {"id": 999_999, "code": "abcd", "expires_in": 600}

    monkeypatch.setattr(plex_auth, "create_pin", create_pin)
    past = time.monotonic() - 10
    auth_external._pending_pins.clear()
    auth_external._pending_pins.update({n: ("x", past) for n in range(auth_external.MAX_PENDING_PINS)})
    try:
        assert client().post("/api/auth/plex/pin").status_code == 200
        assert list(auth_external._pending_pins) == [999_999]
    finally:
        auth_external._pending_pins.clear()


def test_signed_in_member_cannot_fill_the_global_counter(fresh):  # noqa: F811
    """Les échecs d'un appareil connu ne comptent que pour son compte : un membre ne peut pas saturer le plafond
    global (qui bloque les nouveaux appareils de tout le monde)."""
    admin = client()
    setup_admin(admin)
    alice = member(admin, "alice")
    for _ in range(3):
        for _ in range(7):
            assert alice.post("/api/auth/login", json={"username": "alice", "password": "faux"}).status_code == 401
        assert alice.post("/api/auth/login", json={"username": "alice", "password": "nouveau-mdp-alice"}).status_code == 200
    for _ in range(5):
        assert alice.post("/api/auth/password", json={"current_password": "faux", "new_password": "peu-importe-1"}).status_code == 403
    assert auth.login_limiter._count("all:") == 0


def test_open_session_keeps_sensitive_changes_during_a_distributed_attack(fresh):  # noqa: F811
    """Plafond global atteint (attaque répartie) : une session ouverte peut toujours changer son mot de passe."""
    admin = client()
    setup_admin(admin)
    for _ in range(auth.RateLimiter.LIMITS["all"]):
        auth.login_limiter.fail("all:")
    r = admin.post("/api/auth/password", json={"current_password": "motdepasse-admin", "new_password": "motdepasse-admin-2"})
    assert r.status_code == 200, r.text
    assert admin.post("/api/auth/2fa/setup", json={"password": "motdepasse-admin-2"}).status_code == 200


def test_simultaneous_wrong_codes_are_all_counted(fresh):  # noqa: F811
    """2FA : des essais envoyés en même temps ne passent pas sous le compteur (5 par ticket, échecs comptés un à un)."""
    admin = client()
    setup_admin(admin)
    secret = admin.post("/api/auth/2fa/setup", json={"password": "motdepasse-admin"}).json()["secret"]
    assert admin.post("/api/auth/2fa/enable", json={"code": totp.code_at(secret, time.time())}).status_code == 200
    c = client()
    ticket = c.post("/api/auth/login", json={"username": "morgan", "password": "motdepasse-admin"}).json()["ticket"]
    checked = []
    real = auth_router._check_code

    def slow(db, user, code):
        time.sleep(0.05)  # laisse les autres requêtes arriver pendant la vérification
        checked.append(code)
        return real(db, user, code)

    auth_router._check_code = slow
    try:
        threads = [threading.Thread(target=lambda: client().post("/api/auth/login/2fa", json={"ticket": ticket, "code": "000000"})) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    finally:
        auth_router._check_code = real
    assert len(checked) <= 5
    with SessionLocal() as db:
        assert db.get(User, 1).totp_failures == len(checked)
        assert db.execute(select(Notification).execution_options(all_users=True)).scalars().all() == []


# --- Entrées bornées ---------------------------------------------------------------------


def test_oversized_request_bodies_are_refused(fresh):  # noqa: F811
    """Corps de requête démesuré, annoncé ou envoyé par morceaux : refusé avant d'être gardé en mémoire."""
    c = client()
    big = b'{"username": "' + b"a" * (2 * 1024 * 1024) + b'", "password": "x"}'
    assert c.post("/api/auth/login", content=big, headers={"content-type": "application/json"}).status_code == 413

    def chunks():
        for _ in range(40):
            yield b"a" * 65536

    assert c.post("/api/auth/login", content=chunks(), headers={"content-type": "application/json"}).status_code == 413
    assert c.post("/api/auth/login", json={"username": "x", "password": "y"}).status_code == 401  # taille normale : traité


def test_plex_image_path_cannot_reach_another_resource(fresh):  # noqa: F811
    from app.services.errors import ServiceError
    from app.services.plex_client import PlexClient

    plex = PlexClient("http://plex.test:32400", "jeton")
    for path in ("/library/../photo/:/transcode?url=http://10.0.0.1/", "/library/metadata/1/thumb/2?url=x", "/library/%2e%2e/identity",
                 "http://10.0.0.1/library/x", "/library/metadata/1/../../../identity"):
        try:
            asyncio.run(plex.image(path, 342))
            raise AssertionError(f"chemin accepté : {path}")
        except ServiceError as e:
            assert e.status == 400


def test_settings_and_stats_inputs_are_bounded(fresh):  # noqa: F811
    admin = client()
    setup_admin(admin)
    assert admin.put("/api/settings", json={"letterboxd_username": " alex_b "}).json()["letterboxd_username"] == "alex_b"
    assert admin.put("/api/settings", json={"letterboxd_username": "../film/x"}).status_code == 422
    assert admin.put("/api/settings", json={"tmdb_api_key": "k" * 501}).status_code == 422
    assert admin.put("/api/settings", json={"active_platforms": list(range(301))}).status_code == 422
    assert admin.get("/api/stats/events", params={"start": "pas-une-date", "end": "2026-01-01"}).status_code == 422
    assert admin.get("/api/stats/activity", params={"tz": 10**9}).status_code == 422
    assert admin.get("/api/notifications", params={"limit": -1}).status_code == 422
    assert admin.get("/api/search", params={"q": "x" * 201}).status_code == 422
    assert admin.post("/api/library/watchlist", json={"tmdb_id": 1, "media_type": "movie", "title": "x" * 301}).status_code == 422
    assert admin.post("/api/episodes/mark", json={"tmdb_id": 1, "episodes": [{"season": 1, "episode": n} for n in range(2001)]}).status_code == 422


def test_cinema_requests_cannot_be_steered_to_another_address(monkeypatch):
    """Ville, cinéma et date sont placés dans l'adresse demandée au site des séances : rien d'autre qu'un nom de ville,
    un identifiant de cinéma et une date."""
    from app.services import allocine_client
    from app.services.errors import ServiceError

    asked = []

    async def get(path, ttl, country="FR"):
        asked.append(path)
        return {}

    monkeypatch.setattr(allocine_client, "_get", get)
    asyncio.run(allocine_client.search("../../autre/page?x=1#y"))
    asyncio.run(allocine_client.search("Saint-Étienne du Rouvray"))
    assert asked == ["/localization_city/autre-page-x-1-y", "/localization_city/saint-%C3%A9tienne-du-rouvray"]
    for theater, day in (("P0001/../x", "2026-01-01"), ("P0001", "2026-01-01/../x"), ("", "2026-01-01")):
        try:
            asyncio.run(allocine_client.showtimes(theater, day))
            raise AssertionError("accepté")
        except ServiceError as e:
            assert e.status == 422
    assert len(asked) == 2


# --- Autres administrateurs --------------------------------------------------------------


def test_main_admin_chooses_whether_other_admins_see_the_media_server(fresh):  # noqa: F811
    """Le serveur multimédia (tableau de bord, bibliothèque avec le jeton du serveur) n'est partagé avec les autres
    administrateurs que si l'administrateur principal le veut ; lui seul change ce réglage."""
    admin = client()
    setup_admin(admin)
    sam = member(admin, "sam")
    sam_id = _ids(admin)["sam"]
    assert admin.patch(f"/api/admin/users/{sam_id}", json={"role": "admin"}).status_code == 200
    with SessionLocal() as db:
        s = db.get(UserSettings, 1)
        s.plex_url, s.plex_token = "http://plex.test:32400", "jeton-du-serveur"
        db.commit()
    # Par défaut (comme avant) : partagé
    assert sam.get("/api/auth/me").json()["user"]["server_admin"] is True
    assert sam.get("/api/settings/status").json()["plex"]["configured"] is True
    assert [x["id"] for x in sam.get("/api/admin/servers").json()["results"]] == ["plex"]
    # Seul l'administrateur principal change le réglage
    assert sam.put("/api/settings", json={"admins_full_access": False}).status_code == 403
    assert admin.put("/api/settings", json={"admins_full_access": False}).json()["admins_full_access"] is False
    # Non partagé : l'autre administrateur n'a pas plus accès au serveur qu'un membre, mais gère toujours les comptes
    assert sam.get("/api/auth/me").json()["user"]["server_admin"] is False
    assert sam.get("/api/settings/status").json()["plex"]["configured"] is False
    assert sam.get("/api/admin/servers").json()["results"] == []
    assert sam.get("/api/admin/plex/dashboard").status_code == 403
    assert sam.post("/api/admin/plex/scan").status_code in (403, 422)
    assert sam.get("/api/admin/users").status_code == 200
    # … ni les réglages du serveur (écriture, adresses, aperçu des clés), ni les sauvegardes (elles contiennent les jetons)
    assert sam.put("/api/settings", json={"tmdb_api_key": "autre-cle"}).status_code == 403
    assert sam.get("/api/settings").json()["plex_url"] == ""
    assert sam.get("/api/admin/backups").status_code == 403
    assert sam.post("/api/admin/backups").status_code == 403
    assert sam.get("/api/plex/servers").status_code == 403
    assert sam.get("/api/admin/plex/stats").status_code == 403  # visionnages de tous les comptes du serveur
    assert admin.get("/api/admin/backups").status_code == 200
    # L'administrateur principal garde tout
    assert admin.get("/api/settings/status").json()["plex"]["configured"] is True
    assert [x["id"] for x in admin.get("/api/admin/servers").json()["results"]] == ["plex"]


def test_youtube_sources_are_recognised_by_exact_host(monkeypatch):
    """« evilyoutube.com » n'est pas YouTube : traité comme un site quelconque (téléchargement protégé)."""
    from app.services import news, safe_fetch
    from app.services.errors import ServiceError

    seen = []

    async def fetch(url, timeout=15.0):
        seen.append(url)
        raise ServiceError("news", "arrêt du test", 502)

    monkeypatch.setattr(safe_fetch, "fetch", fetch)
    try:
        asyncio.run(news.resolve("https://evilyoutube.com/channel/UC" + "a" * 22))
    except ServiceError:
        pass
    assert seen == ["https://evilyoutube.com/channel/UC" + "a" * 22]


def test_other_admins_cannot_take_over_the_main_admin(fresh, monkeypatch):  # noqa: F811
    """Un autre administrateur ne peut ni changer le mot de passe du compte principal, ni retirer sa double
    authentification, ni s'attribuer le compte Plex du propriétaire du serveur."""
    admin = client()
    setup_admin(admin)
    sam = member(admin, "sam")
    assert admin.patch(f"/api/admin/users/{_ids(admin)['sam']}", json={"role": "admin"}).status_code == 200
    assert sam.patch("/api/admin/users/1", json={"password": "pris-par-sam-123"}).status_code == 403
    assert sam.patch("/api/admin/users/1", json={"reset_two_factor": True}).status_code == 403
    assert sam.patch("/api/admin/users/1", json={"display_name": "Morgan"}).status_code == 200  # le reste est permis
    assert client().post("/api/auth/login", json={"username": "morgan", "password": "motdepasse-admin"}).status_code == 200
    # Compte Plex du propriétaire du serveur : seulement pour le compte administrateur principal
    with SessionLocal() as db:
        s = db.get(UserSettings, 1)
        s.plex_account_token, s.plex_machine_id, s.plex_client_id = "jeton-plex-tv", "machine", "client"
        db.commit()

    async def account_info(cid, token):
        return {"id": 4242, "title": "Morgan", "username": "morgan", "thumb": ""}

    async def server_users(cid, token, machine):
        return []

    monkeypatch.setattr(plex_auth, "account_info", account_info)
    monkeypatch.setattr(plex_auth, "server_users", server_users)
    assert sam.post("/api/admin/plex/accounts", json={"plex_user_id": 4242}).status_code == 403
    r = admin.post("/api/admin/plex/accounts", json={"plex_user_id": 4242})
    assert r.status_code == 200 and r.json()["plex"]["id"] == 4242
    assert admin.post("/api/admin/plex/scan", params={"section_id": "1/../../identity"}).status_code == 422


# --- Durcissements -----------------------------------------------------------------------


def test_temporary_password_expires(fresh):  # noqa: F811
    """Mot de passe provisoire jamais utilisé : inutilisable après 7 jours ; l'administrateur en redonne un."""
    admin = client()
    setup_admin(admin)
    alice = add_member(admin)
    assert alice["temp_password_expired"] is False
    with SessionLocal() as db:
        u = db.get(User, alice["id"])
        assert timedelta(days=6) < u.temp_password_until - utcnow() <= timedelta(days=7)
        u.temp_password_until = utcnow() - timedelta(minutes=1)
        db.commit()
    assert client().post("/api/auth/login", json={"username": "alice", "password": "faux-mot-de-passe"}).status_code == 401
    r = client().post("/api/auth/login", json={"username": "alice", "password": "provisoire1"})
    assert r.status_code == 403 and "expiré" in r.json()["detail"]
    assert next(u for u in admin.get("/api/admin/users").json()["results"] if u["username"] == "alice")["temp_password_expired"] is True
    assert admin.patch(f"/api/admin/users/{alice['id']}", json={"password": "provisoire2"}).status_code == 200
    c = login("alice", "provisoire2")
    assert c.post("/api/auth/password", json={"new_password": "nouveau-mdp-alice"}).status_code == 200
    with SessionLocal() as db:
        assert db.get(User, alice["id"]).temp_password_until is None  # mot de passe choisi : plus d'échéance


def test_device_cookie_is_dated(fresh):  # noqa: F811
    """Cookie d'appareil : la date d'émission est signée ; trop ancien, modifié ou à l'ancien format, il ne vaut rien."""
    from types import SimpleNamespace

    def known(value):
        return auth.known_device(SimpleNamespace(cookies={auth.DEVICE_COOKIE: value}))

    now = int(time.time())
    good = f"7.{now}.abc.{auth._device_sig(7, now, 'abc')}"
    assert known(good) == 7
    old = now - auth.DEVICE_DAYS * 86400 - 60
    assert known(f"7.{old}.abc.{auth._device_sig(7, old, 'abc')}") is None  # expiré
    assert known(f"7.{now + 3600}.abc.{auth._device_sig(7, now, 'abc')}") is None  # date modifiée
    assert known(f"8.{now}.abc.{auth._device_sig(7, now, 'abc')}") is None  # autre compte
    assert known("7.abc.0123456789abcdef0123456789abcdef") is None  # ancien format sans date
    assert known("") is None


def test_recovery_codes_are_keyed_and_old_ones_still_work(fresh):  # noqa: F811
    import hashlib

    code = totp.new_recovery_codes()[0]
    keyed = totp.hash_recovery(code)
    assert keyed.startswith("k1:") and keyed != "k1:" + hashlib.sha256(totp._norm(code).encode()).hexdigest()
    legacy = hashlib.sha256(totp._norm(code).encode()).hexdigest()  # code créé par une version précédente
    assert totp.use_recovery(code, [keyed, "autre"]) == ["autre"]
    assert totp.use_recovery(code, [legacy, "autre"]) == ["autre"]
    assert totp.use_recovery("zzzz-zzzz", [keyed, legacy]) is None


# --- Jetons chiffrés dans la base --------------------------------------------------------


def _raw(sql: str):
    from sqlalchemy import text

    from app.database import engine

    with engine.connect() as conn:
        return conn.execute(text(sql)).all()


def test_tokens_are_encrypted_in_the_database(fresh):  # noqa: F811
    """La base (donc ses sauvegardes) ne contient aucun jeton, clé d'API ni secret 2FA en clair."""
    admin = client()
    setup_admin(admin)
    assert admin.put("/api/settings", json={"tmdb_api_key": "cle-tmdb-en-clair", "seerr_url": "http://seerr.test", "seerr_api_key": "cle-seerr-en-clair"}).status_code == 200
    with SessionLocal() as db:
        s = db.get(UserSettings, 1)
        s.plex_token, s.trakt_access_token, s.jellyfin_token = "jeton-plex-en-clair", "jeton-trakt-en-clair", "jeton-jellyfin-en-clair"
        db.commit()
    secret = admin.post("/api/auth/2fa/setup", json={"password": "motdepasse-admin"}).json()["secret"]
    assert admin.post("/api/auth/2fa/enable", json={"code": totp.code_at(secret, time.time())}).status_code == 200
    dump = repr(_raw("SELECT * FROM user_settings")) + repr(_raw("SELECT * FROM users"))
    for clear in ("cle-tmdb-en-clair", "cle-seerr-en-clair", "jeton-plex-en-clair", "jeton-trakt-en-clair", "jeton-jellyfin-en-clair", secret):
        assert clear not in dump
    assert dump.count("enc1:") == 6
    # Le code, lui, lit les valeurs en clair, et l'aperçu masqué de l'admin fonctionne toujours
    with SessionLocal() as db:
        s = db.get(UserSettings, 1)
        assert (s.tmdb_api_key, s.plex_token, s.trakt_access_token) == ("cle-tmdb-en-clair", "jeton-plex-en-clair", "jeton-trakt-en-clair")
        assert db.get(User, 1).totp_secret == secret
    assert admin.get("/api/settings").json()["secrets"]["tmdb_api_key"].endswith("lair")
    # Deux écritures de la même valeur ne donnent pas le même chiffré (pas de comparaison possible entre comptes)
    from app.services import crypto

    assert crypto.encrypt("x") != crypto.encrypt("x") and crypto.decrypt(crypto.encrypt("x")) == "x"


def test_plain_tokens_of_an_older_database_are_encrypted_at_startup(fresh):  # noqa: F811
    from sqlalchemy import text

    from app.database import engine, init_db

    admin = client()
    setup_admin(admin)
    with engine.begin() as conn:  # base d'une version précédente : valeurs en clair
        conn.execute(text("UPDATE user_settings SET tmdb_api_key = 'ancienne-cle', plex_token = 'ancien-jeton', trakt_refresh_token = '' WHERE id = 1"))
        conn.execute(text("UPDATE users SET totp_pending = 'ANCIENSECRET' WHERE id = 1"))
    init_db()
    row = _raw("SELECT tmdb_api_key, plex_token, trakt_refresh_token FROM user_settings WHERE id = 1")[0]
    assert row[0].startswith("enc1:") and row[1].startswith("enc1:") and row[2] == ""  # vide : laissé vide
    assert _raw("SELECT totp_pending FROM users WHERE id = 1")[0][0].startswith("enc1:")
    with SessionLocal() as db:
        s = db.get(UserSettings, 1)
        assert (s.tmdb_api_key, s.plex_token) == ("ancienne-cle", "ancien-jeton")
        assert db.get(User, 1).totp_pending == "ANCIENSECRET"
    init_db()  # second démarrage : rien n'est chiffré deux fois
    assert _raw("SELECT tmdb_api_key FROM user_settings WHERE id = 1")[0][0] == row[0]


def test_database_restored_without_the_server_key_starts_disconnected(fresh, monkeypatch):  # noqa: F811
    """Sauvegarde restaurée sur une installation qui n'a pas la clé du serveur : aucun jeton lisible, aucune erreur ;
    les services sont à reconnecter, la 2FA à réactiver, et l'on peut enregistrer de nouvelles valeurs."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    from app.services import crypto

    admin = client()
    setup_admin(admin)
    admin.put("/api/settings", json={"tmdb_api_key": "cle-tmdb"})
    secret = admin.post("/api/auth/2fa/setup", json={"password": "motdepasse-admin"}).json()["secret"]
    admin.post("/api/auth/2fa/enable", json={"code": totp.code_at(secret, time.time())})
    other = AESGCM(b"k" * 32)
    monkeypatch.setattr(crypto, "_aead", lambda: other)  # autre clé de serveur
    status = admin.get("/api/settings/status")
    assert status.status_code == 200 and status.json()["tmdb"]["configured"] is False
    r = client().post("/api/auth/login", json={"username": "morgan", "password": "motdepasse-admin"})
    assert r.status_code == 200 and r.json()["user"]["two_factor"] is False  # mot de passe seul : 2FA à réactiver
    assert admin.put("/api/settings", json={"tmdb_api_key": "nouvelle-cle"}).status_code == 200
    with SessionLocal() as db:
        assert db.get(UserSettings, 1).tmdb_api_key == "nouvelle-cle"
