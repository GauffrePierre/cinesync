"""Comptes : migration d'une base mono-utilisateur, cloisonnement des données, connexion, demandes."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

import app.database as database
from app.database import Base, SessionLocal, bind_user, engine, init_db
from app.main import app
from app.models import MediaRequest, MediaState, Notification, SwipeHistory, User, UserSettings
from app.services import auth
from app.services.cache import cache

ORIGIN = {"Origin": "http://testserver"}


@pytest.fixture
def fresh():
    from tests.conftest import assert_test_database

    assert_test_database()
    Base.metadata.drop_all(engine)
    init_db()
    cache.clear()
    auth.login_limiter._fails.clear()
    auth.jellyfin_limiter._fails.clear()
    auth.jellyfin_device_limiter._fails.clear()
    auth._protect = None
    from app.services import quick_connect

    quick_connect.clear()
    yield


def client() -> TestClient:
    return TestClient(app, headers=ORIGIN)


def setup_admin(c: TestClient, password="motdepasse-admin") -> dict:
    r = c.post("/api/auth/setup", json={"code": database.setup_code, "username": "Morgan", "password": password})
    assert r.status_code == 200, r.text
    return r.json()


def add_member(admin: TestClient, username="alice", password="provisoire1") -> dict:
    r = admin.post("/api/admin/users", json={"username": username, "password": password, "display_name": username.title()})
    assert r.status_code == 200, r.text
    return r.json()


def login(username, password) -> TestClient:
    c = client()
    r = c.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return c


def link_plex(user_id: int) -> None:
    """Simule un compte relié au serveur Plex : adresse du serveur (réglage partagé) + jeton propre au compte."""
    with SessionLocal() as db:
        db.get(UserSettings, 1).plex_url = "http://plex.test:32400"
        db.get(UserSettings, 1).plex_token = "jeton-du-serveur"
        db.get(UserSettings, user_id).plex_token = f"jeton-du-compte-{user_id}"
        db.commit()


# --- Migration ---------------------------------------------------------------------------


def test_single_user_database_is_migrated_to_admin():
    Base.metadata.drop_all(engine)
    with engine.begin() as conn:
        for t in ("users", "auth_sessions"):
            conn.execute(text(f"DROP TABLE IF EXISTS {t}"))
        # Schéma d'avant les comptes : unicité sur (tmdb_id, media_type), pas de user_id
        conn.execute(text(
            "CREATE TABLE media_state (id INTEGER PRIMARY KEY, tmdb_id INTEGER, media_type VARCHAR(8), title VARCHAR, "
            "watchlist_sources TEXT DEFAULT '[]', CONSTRAINT uq_media_state UNIQUE (tmdb_id, media_type))"
        ))
        conn.execute(text("CREATE INDEX ix_media_state_tmdb_id ON media_state (tmdb_id)"))
        conn.execute(text("INSERT INTO media_state (tmdb_id, media_type, title, watchlist_sources) VALUES (603, 'movie', 'Matrix', '[\"trakt\"]')"))
        conn.execute(text(
            "CREATE TABLE swipe_history (id INTEGER PRIMARY KEY, tmdb_id INTEGER, media_type VARCHAR(8), action VARCHAR(16), "
            "rating INTEGER, title VARCHAR, created_at DATETIME, CONSTRAINT uq_swipe_media UNIQUE (tmdb_id, media_type))"
        ))
        conn.execute(text("INSERT INTO swipe_history (tmdb_id, media_type, action, title) VALUES (11, 'movie', 'like', 'Star Wars')"))
        conn.execute(text("CREATE TABLE user_settings (id INTEGER PRIMARY KEY, tmdb_api_key VARCHAR DEFAULT '')"))
        conn.execute(text("INSERT INTO user_settings (id, tmdb_api_key) VALUES (1, 'cle-existante')"))
    init_db()
    with SessionLocal() as db:
        admin = db.get(User, 1)
        assert admin.role == "admin" and not admin.password_hash
        assert database.setup_required(db) and database.setup_code
        assert db.get(UserSettings, 1).tmdb_api_key == "cle-existante"
        rows = db.execute(select(MediaState).execution_options(all_users=True)).scalars().all()
        assert [(r.user_id, r.tmdb_id, r.title) for r in rows] == [(1, 603, "Matrix")]
        assert db.execute(select(SwipeHistory.user_id)).scalars().all() == [1]
        # Un autre compte peut maintenant avoir le même titre
        db.add(MediaState(user_id=2, tmdb_id=603, media_type="movie"))
        db.commit()


# --- Cloisonnement --------------------------------------------------------------------------


def test_rows_are_scoped_to_the_bound_user(fresh):
    with SessionLocal() as db:
        db.add(User(id=2, username="alice"))
        db.commit()
        bind_user(db, 1)
        db.add_all([MediaState(tmdb_id=1, media_type="movie"), Notification(message="pour l'admin")])
        db.commit()
        bind_user(db, 2)
        db.add(MediaState(tmdb_id=2, media_type="movie"))
        db.commit()
        assert [r.tmdb_id for r in db.execute(select(MediaState)).scalars()] == [2]
        assert db.execute(select(Notification)).scalars().all() == []
        bind_user(db, 1)
        assert [r.tmdb_id for r in db.execute(select(MediaState)).scalars()] == [1]


def test_unbound_session_cannot_create_personal_rows(fresh):
    with SessionLocal() as db:
        db.add(MediaState(tmdb_id=1, media_type="movie"))
        with pytest.raises(RuntimeError):
            db.commit()


def test_members_do_not_see_each_other(fresh):
    admin = client()
    setup_admin(admin)
    add_member(admin)
    alice = login("alice", "provisoire1")
    alice.post("/api/auth/password", json={"new_password": "nouveau-mdp-alice"})
    r = alice.post("/api/library/watchlist", json={"tmdb_id": 603, "media_type": "movie", "title": "Matrix"})
    assert r.status_code == 200, r.text
    assert "movie:603" in alice.get("/api/library/keys").json()["watchlist"]
    assert "movie:603" not in admin.get("/api/library/keys").json()["watchlist"]


# --- Connexion ---------------------------------------------------------------------------


def test_everything_requires_a_session(fresh):
    c = client()
    assert c.get("/api/settings").status_code == 401
    me = c.get("/api/auth/me").json()
    assert me["user"] is None and me["setup_required"] is True


def test_setup_needs_the_code_and_happens_once(fresh):
    c = client()
    r = c.post("/api/auth/setup", json={"code": "FAUX-CODE-0", "username": "morgan", "password": "motdepasse-admin"})
    assert r.status_code == 403
    me = setup_admin(c)
    assert me["user"]["is_admin"] and me["user"]["username"] == "morgan" and not me["setup_required"]
    assert c.get("/api/settings").status_code == 200
    assert client().post("/api/auth/setup", json={"code": "x", "username": "intrus", "password": "motdepasse-x"}).status_code == 409


def test_temporary_password_must_be_changed_first(fresh):
    admin = client()
    setup_admin(admin)
    add_member(admin)
    alice = login("alice", "provisoire1")
    assert alice.get("/api/auth/me").json()["user"]["must_change_password"] is True
    assert alice.get("/api/settings").status_code == 403
    assert alice.post("/api/auth/password", json={"new_password": "court"}).status_code == 422
    assert alice.post("/api/auth/password", json={"new_password": "nouveau-mdp-alice"}).status_code == 200
    assert alice.get("/api/settings").status_code == 200
    # Ensuite, l'ancien mot de passe est exigé
    assert alice.post("/api/auth/password", json={"current_password": "faux", "new_password": "encore-un-autre"}).status_code == 403


def test_wrong_passwords_are_rate_limited(fresh):
    admin = client()
    setup_admin(admin)
    c = client()
    codes = [c.post("/api/auth/login", json={"username": "morgan", "password": f"faux{i}"}).status_code for i in range(9)]
    assert codes[:8] == [401] * 8 and codes[8] == 429


def test_logout_and_cross_site_requests(fresh):
    admin = client()
    setup_admin(admin)
    evil = TestClient(app, headers={"Origin": "https://evil.example"}, cookies=admin.cookies)
    assert evil.put("/api/settings", json={"theme": "dark"}).status_code == 403
    assert admin.post("/api/auth/logout").status_code == 200
    assert admin.get("/api/settings").status_code == 401


def test_members_cannot_touch_server_settings_or_admin(fresh):
    admin = client()
    setup_admin(admin)
    add_member(admin)
    alice = login("alice", "provisoire1")
    alice.post("/api/auth/password", json={"new_password": "nouveau-mdp-alice"})
    assert alice.put("/api/settings", json={"tmdb_api_key": "vol"}).status_code == 403
    assert alice.put("/api/settings", json={"theme": "dark", "country_code": "FR"}).status_code == 200
    assert alice.get("/api/admin/users").status_code == 403
    assert alice.post("/api/plex/auth/pin").status_code == 403
    s = alice.get("/api/settings").json()
    assert s["theme"] == "dark" and s["plex_url"] == ""
    assert admin.get("/api/settings").json()["theme"] != "dark"


def test_deactivated_member_is_logged_out(fresh):
    admin = client()
    setup_admin(admin)
    member = add_member(admin)
    alice = login("alice", "provisoire1")
    admin.patch(f"/api/admin/users/{member['id']}", json={"active": False})
    assert alice.get("/api/auth/me").json()["user"] is None
    assert client().post("/api/auth/login", json={"username": "alice", "password": "provisoire1"}).status_code == 401


def test_last_admin_is_protected(fresh):
    admin = client()
    me = setup_admin(admin)
    assert admin.patch(f"/api/admin/users/{me['user']['id']}", json={"role": "member"}).status_code == 409
    assert admin.delete(f"/api/admin/users/{me['user']['id']}").status_code == 409


# --- Demandes ------------------------------------------------------------------------------


def test_member_requests_go_to_the_admin_queue(fresh):
    admin = client()
    setup_admin(admin)
    member = add_member(admin)
    link_plex(member["id"])
    alice = login("alice", "provisoire1")
    alice.post("/api/auth/password", json={"new_password": "nouveau-mdp-alice"})
    r = alice.post("/api/requests", json={"tmdb_id": 603, "media_type": "movie", "title": "Matrix"}).json()
    assert r["created"] and r["request"]["status"] == "pending" and r["request"]["user_name"] == "Alice"
    # L'admin est prévenu et voit la demande dans la file de tous les comptes
    assert any(n["kind"] == "request" for n in admin.get("/api/notifications").json()["results"])
    queue = admin.get("/api/requests?scope=all").json()
    assert [q["title"] for q in queue["results"]] == ["Matrix"]
    assert admin.get("/api/requests").json()["results"] == []  # ses propres demandes
    assert alice.get("/api/requests?scope=all").status_code == 403
    # Le membre ne peut pas valider sa demande ; l'admin oui, et le membre est prévenu
    rid = r["request"]["id"]
    assert alice.patch(f"/api/requests/{rid}", json={"status": "available"}).status_code == 403
    assert admin.patch(f"/api/requests/{rid}", json={"status": "available"}).status_code == 200
    assert any("disponible" in n["message"] for n in alice.get("/api/notifications").json()["results"])
    # Suppression du compte : ses données partent avec lui
    assert admin.delete(f"/api/admin/users/{member['id']}").status_code == 200
    with SessionLocal() as db:
        assert db.execute(select(MediaRequest).execution_options(all_users=True)).scalars().all() == []


# --- Version personnelle -----------------------------------------------------------------


def test_personal_mode_needs_no_login(fresh, monkeypatch):
    from app.config import config

    monkeypatch.setattr(config, "cinesync_mode", "personal")
    c = client()
    me = c.get("/api/auth/me").json()
    assert me["mode"] == "personal" and not me["setup_required"] and me["user"]["is_admin"]
    assert c.get("/api/settings").status_code == 200
    assert c.post("/api/library/watchlist", json={"tmdb_id": 603, "media_type": "movie", "title": "Matrix"}).status_code == 200
    # Pas de comptes de la famille dans cette version (connexion seulement si un mot de passe est défini)
    assert c.post("/api/auth/login", json={"username": "admin", "password": "x"}).status_code == 401
    assert c.post("/api/admin/users", json={"username": "bob", "password": "motdepasse1"}).status_code == 409
    # Toujours protégé contre les requêtes d'un autre site
    evil = TestClient(app, headers={"Origin": "https://evil.example"})
    assert evil.put("/api/settings", json={"theme": "dark"}).status_code == 403


def test_interface_mime_types():
    """Image Docker sans /etc/mime.types : les logos .webp doivent quand même partir en image/webp (« nosniff »)."""
    import mimetypes

    from app.main import register_mime_types

    mimetypes.init(files=[])  # comme dans python:3.12-slim
    try:
        register_mime_types()
        assert mimetypes.guess_type("icons/logo-mark.webp")[0] == "image/webp"
        assert mimetypes.guess_type("favicon.ico")[0] in ("image/vnd.microsoft.icon", "image/x-icon")
    finally:
        mimetypes.init()
        register_mime_types()


def test_security_headers(fresh):
    r = client().get("/api/health")
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["x-frame-options"] == "DENY"


# --- Revue de sécurité : régressions ------------------------------------------------------


def member(admin: TestClient, username="alice") -> TestClient:
    add_member(admin, username)
    c = login(username, "provisoire1")
    c.post("/api/auth/password", json={"new_password": f"nouveau-mdp-{username}"})
    return c


def test_members_cannot_bypass_the_request_queue(fresh):
    admin = client()
    setup_admin(admin)
    alice = member(admin)
    # L'ancien point d'accès direct à Seerr n'existe plus
    assert alice.post("/api/seerr/request", json={"tmdb_id": 603, "media_type": "movie"}).status_code in (404, 405)


def test_server_plex_pin_must_be_created_by_this_admin(fresh):
    admin = client()
    setup_admin(admin)
    # Lien piégé : un code créé ailleurs (par un attaquant) est refusé, et un GET ne fait plus rien
    assert admin.get("/api/plex/auth/pin/123456").status_code == 405
    assert admin.post("/api/plex/auth/pin/123456").status_code == 410


def test_csrf_check_compares_scheme_host_and_port(fresh):
    admin = client()
    setup_admin(admin)
    for origin in ("http://testserver:8080", "https://testserver", "http://evil.example"):
        other = TestClient(app, headers={"Origin": origin}, cookies=admin.cookies)
        assert other.put("/api/settings", json={"theme": "dark"}).status_code == 403, origin
    assert admin.put("/api/settings", json={"theme": "dark"}).status_code == 200


def test_attacker_cannot_lock_an_account_from_one_address(fresh):
    admin = client()
    setup_admin(admin)
    # 8 échecs d'une adresse bloquent cette adresse pour ce compte…
    for i in range(8):
        client().post("/api/auth/login", json={"username": "morgan", "password": f"faux{i}"})
    assert client().post("/api/auth/login", json={"username": "morgan", "password": "motdepasse-admin"}).status_code == 429
    # …mais le compte reste utilisable depuis une autre adresse
    other = TestClient(app, headers=ORIGIN, client=("203.0.113.9", 50000))
    assert other.post("/api/auth/login", json={"username": "morgan", "password": "motdepasse-admin"}).status_code == 200
    # L'adresse vient de la connexion : un en-tête X-Forwarded-For forgé ne change rien
    spoof = TestClient(app, headers={**ORIGIN, "X-Forwarded-For": "198.51.100.1"})
    assert spoof.post("/api/auth/login", json={"username": "morgan", "password": "x"}).status_code == 429


def test_other_members_request_details_stay_private(fresh):
    admin = client()
    setup_admin(admin)
    alice, bob = member(admin, "alice"), member(admin, "bob")
    with SessionLocal() as db:
        ids = [u.id for u in db.query(User).filter(User.username.in_(["alice", "bob"]))]
    for uid in ids:
        link_plex(uid)
    alice.post("/api/requests", json={"tmdb_id": 603, "media_type": "movie", "title": "Matrix", "note": "pour mon anniversaire"})
    r = bob.post("/api/requests", json={"tmdb_id": 603, "media_type": "movie", "title": "Matrix"}).json()
    assert r["created"] is False and r["request"]["status"] == "pending"
    assert "note" not in r["request"] and "requested_by" not in r["request"] and "user_id" not in r["request"]


def test_member_sees_no_server_addresses(fresh):
    admin = client()
    setup_admin(admin)
    admin.put("/api/settings", json={"seerr_url": "http://10.0.0.5:5055", "seerr_api_key": "cle-seerr-secrete"})
    alice = member(admin)
    s = alice.get("/api/settings").json()
    assert s["seerr_url"] == "" and s["plex_url"] == "" and s["secrets"]["seerr_api_key"] == "••••"


def test_hsts_only_on_the_public_domain(monkeypatch):
    import importlib

    from app import main as main_mod
    from app.config import config

    monkeypatch.setattr(config, "public_url", "https://cinesync.example.org")
    monkeypatch.setattr(config, "hsts_seconds", 31536000)
    m = importlib.reload(main_mod)
    try:
        public = TestClient(m.app, headers={"Host": "cinesync.example.org"}).get("/api/health")
        other = TestClient(m.app, headers={"Host": "server.tailnet.ts.net:8443"}).get("/api/health")
        assert public.headers.get("strict-transport-security") == "max-age=31536000"
        assert "strict-transport-security" not in other.headers
    finally:
        monkeypatch.undo()
        importlib.reload(main_mod)


def test_plain_http_on_public_domain_is_redirected(monkeypatch):
    import importlib

    from app import main as main_mod
    from app.config import config

    monkeypatch.setattr(config, "public_url", "https://cinesync.example.org")
    m = importlib.reload(main_mod)
    try:
        r = TestClient(m.app, base_url="http://cinesync.example.org").get("/api/auth/me?x=1", follow_redirects=False)
        assert r.status_code == 308 and r.headers["location"] == "https://cinesync.example.org/api/auth/me?x=1"
        # Une autre adresse (Tailscale, réseau interne) n'est pas concernée
        assert TestClient(m.app, base_url="http://server.tailnet.ts.net:8443").get("/api/health").status_code == 200
        assert TestClient(m.app, base_url="https://cinesync.example.org").get("/api/health").status_code == 200
        # Proxy non reconnu comme proxy de confiance mais qui annonce du HTTPS : pas de boucle de redirection
        loop = TestClient(m.app, base_url="http://cinesync.example.org", headers={"X-Forwarded-Proto": "https"})
        assert loop.get("/api/health", follow_redirects=False).status_code == 200
    finally:
        monkeypatch.undo()
        importlib.reload(main_mod)


def test_personal_mode_can_be_protected_by_a_password(fresh, monkeypatch):
    from app.config import config

    monkeypatch.setattr(config, "cinesync_mode", "personal")
    me = client()
    # Activation : identifiant + mot de passe ; cet appareil reste connecté
    assert me.put("/api/auth/profile", json={"display_name": "Alex", "username": "alex"}).status_code == 200
    # L'accès est encore libre : le premier mot de passe demande le code écrit dans les journaux du serveur,
    # sinon n'importe quel visiteur pourrait le définir et enfermer le propriétaire dehors
    assert me.post("/api/auth/password", json={"new_password": "mon-mot-de-passe"}).status_code == 403
    assert me.post("/api/auth/protect/code").status_code == 200
    assert me.post("/api/auth/password", json={"new_password": "mon-mot-de-passe", "code": "0000-0000-0000"}).status_code == 403
    code = auth._protect[0]
    r = me.post("/api/auth/password", json={"new_password": "mon-mot-de-passe", "code": code.lower()})
    assert r.status_code == 200 and r.json()["user"]["has_password"]
    assert me.post("/api/auth/protect/code").status_code == 409  # déjà protégé : plus de code
    assert me.get("/api/settings").status_code == 200
    # Un autre appareil doit maintenant se connecter
    other = client()
    assert other.get("/api/auth/me").json()["user"] is None
    assert other.get("/api/settings").status_code == 401
    assert other.post("/api/auth/login", json={"username": "alex", "password": "faux-mot-de-passe"}).status_code == 401
    assert other.post("/api/auth/login", json={"username": "alex", "password": "mon-mot-de-passe"}).status_code == 200
    assert other.get("/api/settings").status_code == 200
    # Retrait de la protection (mot de passe actuel exigé) : accès libre à nouveau
    assert other.request("DELETE", "/api/auth/password", json={"current_password": "faux"}).status_code == 403
    assert other.request("DELETE", "/api/auth/password", json={"current_password": "mon-mot-de-passe"}).status_code == 200
    assert client().get("/api/settings").status_code == 200


def test_plex_member_can_also_get_a_password(fresh):
    admin = client()
    setup_admin(admin)
    # Compte Plex (simulé) : l'admin lui donne un mot de passe provisoire
    with SessionLocal() as db:
        db.add(User(id=5, username="sam", display_name="Sam", plex_user_id=4242, plex_username="Sam"))
        db.add(UserSettings(id=5))
        db.commit()
    assert admin.patch("/api/admin/users/5", json={"password": "provisoire-sam"}).status_code == 200
    sam = login("sam", "provisoire-sam")
    assert sam.get("/api/auth/me").json()["user"]["must_change_password"] is True
    assert sam.post("/api/auth/password", json={"new_password": "secret-de-sam"}).status_code == 200
    # Avec Plex, il peut aussi retirer son mot de passe ; un compte local, non
    assert sam.request("DELETE", "/api/auth/password", json={"current_password": "secret-de-sam"}).status_code == 200
    assert admin.request("DELETE", "/api/auth/password", json={"current_password": "motdepasse-admin"}).status_code == 409



def test_member_without_plex_sees_nothing_of_the_admin_plex(fresh):
    admin = client()
    setup_admin(admin)
    alice = member(admin, "alice")
    with SessionLocal() as db:
        alice_id = db.query(User).filter(User.username == "alice").one().id
        db.get(UserSettings, 1).plex_url = "http://plex.test:32400"
        db.get(UserSettings, 1).plex_token = "jeton-du-serveur"
        db.get(UserSettings, 1).plex_server_name = "Serveur de l'admin"
        db.commit()
    # Ni configuré, ni nom du serveur, ni bibliothèque (pas même de démonstration), ni service Plex dans la barre
    st = alice.get("/api/settings/status").json()
    assert st["plex"]["configured"] is False and st["plex"]["server"] is None and "plex" not in st["health"]
    assert alice.get("/api/plex/library").status_code == 409
    assert alice.get("/api/plex/sections").status_code == 409
    assert alice.get("/api/plex/status/movie/603").json() == {"configured": False, "available": False}
    # Pas de demandes d'ajout au serveur Plex
    assert alice.get("/api/requests").json()["allowed"] is False
    assert alice.post("/api/requests", json={"tmdb_id": 603, "media_type": "movie", "title": "Matrix"}).status_code == 403
    # Le même membre, une fois relié à Plex, retrouve tout
    link_plex(alice_id)
    st = alice.get("/api/settings/status").json()
    assert st["plex"]["configured"] is True and st["plex"]["server"] == "Serveur de l'admin" and st["plex"]["own"] is True
    assert alice.get("/api/requests").json()["allowed"] is True
    # L'admin garde l'accès au serveur avec son jeton
    assert admin.get("/api/settings/status").json()["plex"]["configured"] is True


def test_member_sees_no_seerr_address_nor_admin_server(fresh):
    admin = client()
    setup_admin(admin)
    alice = member(admin, "alice")
    with SessionLocal() as db:
        s = db.get(UserSettings, 1)
        s.seerr_url, s.seerr_api_key = "http://10.0.0.5:5055", "cle-seerr"
        s.plex_server_name, s.plex_machine_id = "Serveur de l'admin", "machine-123"
        db.commit()
    # Sans Plex : ni Seerr, ni nom ou identifiant du serveur Plex de l'admin
    assert alice.get("/api/seerr/status/movie/603").json() == {"configured": False}
    st = alice.get("/api/settings").json()
    assert st["plex_server_name"] == "" and st["plex_machine_id"] == ""
    assert "10.0.0.5" not in alice.get("/api/settings").text
    # Ses demandes ne montrent jamais l'adresse de Seerr
    with SessionLocal() as db:
        alice_id = db.query(User).filter(User.username == "alice").one().id
        db.add(MediaRequest(user_id=alice_id, tmdb_id=603, media_type="movie", title="Matrix", status="sent", seerr_url="http://10.0.0.5:5055/movie/603"))
        db.commit()
    link_plex(alice_id)
    assert "10.0.0.5" not in alice.get("/api/requests").text
    assert admin.get("/api/requests?scope=all").json()["results"][0]["seerr_url"].startswith("http://10.0.0.5")


def test_state_changing_trakt_start_is_not_a_get(fresh):
    admin = client()
    setup_admin(admin)
    assert admin.get("/api/trakt/oauth/start").status_code == 405


def test_only_the_main_admin_links_the_plex_server(fresh):
    admin = client()
    setup_admin(admin)
    bob_id = add_member(admin, "bob")["id"]
    admin.patch(f"/api/admin/users/{bob_id}", json={"role": "admin"})
    bob = login("bob", "provisoire1")
    bob.post("/api/auth/password", json={"new_password": "bob-secret-12"})
    assert bob.post("/api/plex/auth/pin").status_code == 403


def test_new_accounts_get_the_first_run_assistant(fresh):
    admin = client()
    setup_admin(admin)
    assert admin.get("/api/settings").json()["onboarding"] == "pending"  # nouvelle installation
    assert admin.put("/api/settings", json={"onboarding": "done"}).json()["onboarding"] == "done"
    alice = member(admin, "alice")
    assert alice.get("/api/settings").json()["onboarding"] == "pending"
    assert admin.get("/api/settings").json()["onboarding"] == "done"  # réglage propre à chaque compte


def test_menu_order_is_saved_per_account(fresh):
    admin = client()
    setup_admin(admin)
    assert admin.get("/api/settings").json()["nav_order"] == []
    r = admin.put("/api/settings", json={"nav_order": ["watchlist", "discover", "watchlist"]})
    assert r.json()["nav_order"] == ["watchlist", "discover"]
    assert admin.put("/api/settings", json={"nav_order": ["<script>"]}).status_code == 422
    assert admin.put("/api/settings", json={"nav_order": []}).json()["nav_order"] == []
