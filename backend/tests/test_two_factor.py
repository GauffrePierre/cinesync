"""Double authentification (TOTP) : calcul des codes, activation, connexion en deux étapes, secours, réinitialisation."""

import time

from app.services import totp
from tests.test_accounts import add_member, client, fresh, login, setup_admin  # noqa: F401 (fixture)


def test_rfc6238_reference_code():
    # Vecteur de la RFC 6238 (secret ASCII « 12345678901234567890 », SHA-1, t = 59 s), sur 6 et 8 chiffres
    secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
    assert totp.code_at(secret, 59) == "287082"
    assert totp.code_at(secret, 59, digits=8) == "94287082"
    assert totp.code_at(secret, 1111111109, digits=8) == "07081804"


def test_verify_tolerates_one_period_and_refuses_replay():
    secret = totp.new_secret()
    now = 1_000_000.0
    code = totp.code_at(secret, now - 30)  # code de la période précédente (horloge du téléphone en retard)
    counter = totp.verify(secret, code, now=now)
    assert counter == int(now // 30) - 1
    assert totp.verify(secret, code, last_counter=counter, now=now) is None  # même code réutilisé
    assert totp.verify(secret, totp.code_at(secret, now - 90), now=now) is None  # trop ancien
    assert totp.verify(secret, "12345", now=now) is None
    assert totp.verify("", "123456", now=now) is None


def test_recovery_codes_are_single_use():
    codes = totp.new_recovery_codes()
    hashes = [totp.hash_recovery(c) for c in codes]
    assert len(set(codes)) == 10
    left = totp.use_recovery(codes[0].upper().replace("-", " "), hashes)  # saisie tolérante
    assert left is not None and len(left) == 9
    assert totp.use_recovery(codes[0], left) is None
    assert totp.use_recovery("zzzz-zzzz", hashes) is None


def _enable(c, password="motdepasse-admin") -> tuple[str, list[str]]:
    assert c.post("/api/auth/2fa/setup", json={"password": "faux"}).status_code == 403  # mot de passe actuel exigé
    r = c.post("/api/auth/2fa/setup", json={"password": password})
    assert r.status_code == 200, r.text
    setup = r.json()
    assert setup["uri"].startswith("otpauth://totp/") and "<svg" in setup["qr_svg"]
    secret = setup["secret"]
    # Pas encore active tant qu'un premier code n'a pas été validé
    assert not c.get("/api/auth/me").json()["user"]["two_factor"]
    assert c.post("/api/auth/2fa/enable", json={"code": "000000"}).status_code == 422
    r = c.post("/api/auth/2fa/enable", json={"code": totp.code_at(secret, time.time())})
    assert r.status_code == 200, r.text
    assert r.json()["user"]["two_factor"] and len(r.json()["recovery_codes"]) == 10
    return secret, r.json()["recovery_codes"]


def _next_code(secret: str) -> str:
    """Code de la période suivante (celui de la période en cours a déjà servi : rejeu refusé)."""
    return totp.code_at(secret, time.time() + 30)


def test_login_requires_the_code_once_enabled(fresh):
    admin = client()
    setup_admin(admin)
    secret, _ = _enable(admin)
    c = client()
    r = c.post("/api/auth/login", json={"username": "morgan", "password": "motdepasse-admin"})
    assert r.status_code == 200
    body = r.json()
    assert body["user"] is None and body["two_factor_required"] and body["ticket"]
    # Le mot de passe seul n'ouvre pas de session
    assert c.get("/api/settings").status_code == 401
    assert c.post("/api/auth/login/2fa", json={"ticket": body["ticket"], "code": "000000"}).status_code == 401
    assert c.post("/api/auth/login/2fa", json={"ticket": "inconnu", "code": _next_code(secret)}).status_code == 410
    r = c.post("/api/auth/login/2fa", json={"ticket": body["ticket"], "code": _next_code(secret)})
    assert r.status_code == 200 and r.json()["user"]["username"] == "morgan"
    assert c.get("/api/settings").status_code == 200
    # Ticket à usage unique
    assert c.post("/api/auth/login/2fa", json={"ticket": body["ticket"], "code": _next_code(secret)}).status_code == 410


def test_ticket_is_dropped_after_five_wrong_codes(fresh):
    admin = client()
    setup_admin(admin)
    secret, _ = _enable(admin)
    c = client()
    ticket = c.post("/api/auth/login", json={"username": "morgan", "password": "motdepasse-admin"}).json()["ticket"]
    for _ in range(5):
        assert c.post("/api/auth/login/2fa", json={"ticket": ticket, "code": "000000"}).status_code == 401
    assert c.post("/api/auth/login/2fa", json={"ticket": ticket, "code": _next_code(secret)}).status_code == 410


def test_recovery_code_logs_in_once(fresh):
    admin = client()
    setup_admin(admin)
    _, codes = _enable(admin)
    for expected in (200, 401):
        c = client()
        ticket = c.post("/api/auth/login", json={"username": "morgan", "password": "motdepasse-admin"}).json()["ticket"]
        assert c.post("/api/auth/login/2fa", json={"ticket": ticket, "code": codes[0]}).status_code == expected


def test_enabling_logs_out_other_devices(fresh):
    admin = client()
    setup_admin(admin)
    other = login("morgan", "motdepasse-admin")
    _enable(admin)
    assert admin.get("/api/settings").status_code == 200
    assert other.get("/api/settings").status_code == 401


def test_disable_needs_a_valid_code(fresh):
    admin = client()
    setup_admin(admin)
    secret, _ = _enable(admin)
    assert admin.post("/api/auth/2fa/disable", json={"code": "000000"}).status_code == 403
    r = admin.post("/api/auth/2fa/disable", json={"code": _next_code(secret)})
    assert r.status_code == 200 and not r.json()["user"]["two_factor"]
    assert login("morgan", "motdepasse-admin").get("/api/settings").status_code == 200


def test_new_recovery_codes_replace_the_old_ones(fresh):
    admin = client()
    setup_admin(admin)
    secret, old = _enable(admin)
    r = admin.post("/api/auth/2fa/recovery-codes", json={"code": _next_code(secret)})
    assert r.status_code == 200 and len(r.json()["recovery_codes"]) == 10
    c = client()
    ticket = c.post("/api/auth/login", json={"username": "morgan", "password": "motdepasse-admin"}).json()["ticket"]
    assert c.post("/api/auth/login/2fa", json={"ticket": ticket, "code": old[0]}).status_code == 401
    assert c.post("/api/auth/login/2fa", json={"ticket": ticket, "code": r.json()["recovery_codes"][0]}).status_code == 200


def test_admin_can_reset_a_lost_phone_but_members_cannot(fresh):
    admin = client()
    setup_admin(admin)
    alice_id = add_member(admin)["id"]
    alice = login("alice", "provisoire1")
    assert alice.post("/api/auth/password", json={"new_password": "alice-secret-1"}).status_code == 200
    _enable(alice, "alice-secret-1")
    assert alice.patch(f"/api/admin/users/{alice_id}", json={"reset_two_factor": True}).status_code == 403
    r = admin.patch(f"/api/admin/users/{alice_id}", json={"reset_two_factor": True})
    assert r.status_code == 200, r.text
    assert login("alice", "alice-secret-1").get("/api/settings").status_code == 200


def test_secret_is_never_exposed(fresh):
    admin = client()
    setup_admin(admin)
    secret, codes = _enable(admin)
    for url in ("/api/auth/me", "/api/admin/users"):
        text = admin.get(url).text
        assert secret not in text and codes[0] not in text


# --- Revue de sécurité : régressions -------------------------------------------------------


def test_active_secret_cannot_be_replaced_without_a_code(fresh):
    admin = client()
    setup_admin(admin)
    _enable(admin)
    assert admin.post("/api/auth/2fa/setup", json={"password": "motdepasse-admin"}).status_code == 409
    assert admin.post("/api/auth/2fa/enable", json={"code": "123456"}).status_code == 409


def test_wrong_codes_lock_the_second_factor_and_warn_the_owner(fresh):
    from app.database import SessionLocal
    from app.models import Notification, User

    admin = client()
    setup_admin(admin)
    secret, _ = _enable(admin)
    for _ in range(10):
        c = client()
        ticket = c.post("/api/auth/login", json={"username": "morgan", "password": "motdepasse-admin"}).json()["ticket"]
        assert c.post("/api/auth/login/2fa", json={"ticket": ticket, "code": "000000"}).status_code == 401
        auth_limits_clear()
    c = client()
    ticket = c.post("/api/auth/login", json={"username": "morgan", "password": "motdepasse-admin"}).json()["ticket"]
    assert c.post("/api/auth/login/2fa", json={"ticket": ticket, "code": _next_code(secret)}).status_code == 429  # même le bon code
    with SessionLocal() as db:
        assert db.get(User, 1).totp_locked_until is not None
        notes = db.query(Notification).execution_options(all_users=True).filter(Notification.user_id == 1).all()
        assert any("double authentification" in n.message for n in notes)


def auth_limits_clear():
    from app.services import auth

    auth.login_limiter._fails.clear()  # simule des essais depuis plusieurs adresses


def test_invented_username_cannot_lock_another_counter(fresh):
    from app.services import auth

    admin = client()
    setup_admin(admin)
    secret, _ = _enable(admin)
    attacker = client()
    for _ in range(60):
        attacker.post("/api/auth/login", json={"username": "2fa:1", "password": "x"})
        attacker.post("/api/auth/login", json={"username": "setup", "password": "x"})
        for k in [k for k in auth.login_limiter._fails if k.startswith(("ip:", "pair:", "all:"))]:
            auth.login_limiter._fails.pop(k)  # simule des adresses différentes
    c = client()
    ticket = c.post("/api/auth/login", json={"username": "morgan", "password": "motdepasse-admin"}).json()["ticket"]
    assert c.post("/api/auth/login/2fa", json={"ticket": ticket, "code": _next_code(secret)}).status_code == 200


def test_known_device_still_signs_in_during_a_distributed_attack(fresh):
    from app.services import auth

    admin = client()
    setup_admin(admin)  # cet appareil reçoit le cookie d'appareil connu
    assert admin.cookies.get(auth.DEVICE_COOKIE)
    for i in range(300):
        auth.login_limiter.fail("all:")  # plafond global atteint par d'autres adresses
    assert client().post("/api/auth/login", json={"username": "morgan", "password": "motdepasse-admin"}).status_code == 429
    assert admin.post("/api/auth/login", json={"username": "morgan", "password": "motdepasse-admin"}).status_code == 200
    # Un faux cookie ne sert à rien
    other = client()
    other.cookies.set(auth.DEVICE_COOKIE, "1.abc.0000")
    assert other.post("/api/auth/login", json={"username": "morgan", "password": "motdepasse-admin"}).status_code == 429


def test_admin_cannot_reset_own_password_or_2fa_from_the_admin_area(fresh):
    admin = client()
    setup_admin(admin)
    assert admin.patch("/api/admin/users/1", json={"password": "nouveau-mdp-123"}).status_code == 409
    assert admin.patch("/api/admin/users/1", json={"reset_two_factor": True}).status_code == 409
    bob_id = add_member(admin, "bob")["id"]
    assert admin.patch(f"/api/admin/users/{bob_id}", json={"role": "admin"}).status_code == 200
    bob = login("bob", "provisoire1")
    assert bob.post("/api/auth/password", json={"new_password": "bob-secret-12"}).status_code == 200
    assert bob.patch("/api/admin/users/1", json={"active": False}).status_code == 409  # compte principal


def test_cross_site_requests_without_origin_are_refused(fresh):
    admin = client()
    setup_admin(admin)
    r = admin.put("/api/settings", json={"theme": "dark"}, headers={"Origin": "", "Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403


def test_plex_sign_in_pin_needs_plex_to_be_configured(fresh):
    assert client().post("/api/auth/plex/pin").status_code == 404


def test_plex_only_account_needs_a_recent_sign_in_to_add_a_password(fresh):
    from datetime import datetime, timedelta

    from app.database import SessionLocal
    from app.models import AuthSession, User

    admin = client()
    setup_admin(admin)
    uid = add_member(admin)["id"]
    alice = login("alice", "provisoire1")
    assert alice.post("/api/auth/password", json={"new_password": "alice-secret-1"}).status_code == 200
    with SessionLocal() as db:  # devient un compte Plex sans mot de passe, session ancienne
        u = db.get(User, uid)
        u.password_hash, u.plex_user_id = "", 4242
        for s in db.query(AuthSession).filter(AuthSession.user_id == uid):
            s.created_at = datetime.utcnow() - timedelta(hours=2)
        db.commit()
    assert alice.post("/api/auth/password", json={"new_password": "mot-de-passe-pirate"}).status_code == 403
    assert alice.post("/api/auth/2fa/setup").status_code == 403
