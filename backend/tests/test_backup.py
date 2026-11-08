"""Sauvegardes de la base : copie lisible, rotation, sauvegarde automatique, accès admin seulement."""

import gzip
import os
import shutil
import sqlite3
import time

import pytest

from app.services import backup
from tests.test_accounts import add_member, client, fresh, login, setup_admin  # noqa: F401 (fixture)


@pytest.fixture
def clean():
    shutil.rmtree(backup.backup_dir(), ignore_errors=True)
    backup.last_error = None
    yield
    shutil.rmtree(backup.backup_dir(), ignore_errors=True)


def _restore(path, tmp_path) -> sqlite3.Connection:
    out = tmp_path / "restored.db"
    out.write_bytes(gzip.decompress(path.read_bytes()))
    return sqlite3.connect(out)


def test_backup_is_a_readable_copy(fresh, clean, tmp_path):  # noqa: F811
    admin = client()
    setup_admin(admin)
    info = backup.create()
    path = backup.backup_dir() / info["name"]
    assert backup.NAME_RE.match(info["name"]) and info["size"] > 0
    assert oct(path.stat().st_mode & 0o777) == "0o600"  # contient des jetons : propriétaire seulement
    db = _restore(path, tmp_path)
    assert db.execute("pragma integrity_check").fetchone()[0] == "ok"
    assert db.execute("select username from users where id = 1").fetchone()[0] == "morgan"


def test_rotation_and_automatic_runs(fresh, clean):  # noqa: F811
    for _ in range(4):
        backup.create()
    assert len(backup.list_backups()) == 4
    assert backup.rotate(2) == 2 and len(backup.list_backups()) == 2
    # Automatique : rien si désactivé ou si une sauvegarde récente existe
    assert backup.run_automatic(False, 7) is None
    assert backup.run_automatic(True, 7) is None
    for item in backup.list_backups():  # vieillit les sauvegardes d'un jour
        p = backup.backup_dir() / item["name"]
        old = time.time() - 24 * 3600
        os.utime(p, (old, old))
    assert backup.run_automatic(True, 2) is not None
    assert len(backup.list_backups()) == 2


def test_only_backup_files_can_be_reached(fresh, clean):  # noqa: F811
    backup.create()
    assert backup.path_of("../cinesync.db") is None
    assert backup.path_of("secret.key") is None
    assert backup.path_of("syncine-20260101-000000.db.gz") is None  # nom valide mais absent
    assert not backup.delete("../cinesync.db")


def test_admin_endpoints(fresh, clean):  # noqa: F811
    admin = client()
    setup_admin(admin)
    r = admin.get("/api/admin/backups").json()
    assert r["enabled"] is True and r["keep"] == 7 and r["items"] == []
    r = admin.post("/api/admin/backups")
    assert r.status_code == 200 and len(r.json()["items"]) == 1
    name = r.json()["items"][0]["name"]
    dl = admin.get(f"/api/admin/backups/{name}")
    assert dl.status_code == 200 and dl.headers["cache-control"] == "no-store"
    assert gzip.decompress(dl.content)[:15] == b"SQLite format 3"
    assert admin.get("/api/admin/backups/..%2Fcinesync.db").status_code == 404
    r = admin.put("/api/admin/backups/settings", json={"enabled": False, "keep": 3}).json()
    assert r["enabled"] is False and r["keep"] == 3
    assert admin.put("/api/admin/backups/settings", json={"keep": 0}).status_code == 422
    assert admin.delete(f"/api/admin/backups/{name}").json()["items"] == []


def test_members_cannot_touch_backups(fresh, clean):  # noqa: F811
    admin = client()
    setup_admin(admin)
    add_member(admin)
    name = admin.post("/api/admin/backups").json()["items"][0]["name"]
    alice = login("alice", "provisoire1")
    assert alice.post("/api/auth/password", json={"new_password": "alice-secret-1"}).status_code == 200
    assert alice.get("/api/admin/backups").status_code == 403
    assert alice.get(f"/api/admin/backups/{name}").status_code == 403
    assert alice.post("/api/admin/backups").status_code == 403
    assert alice.delete(f"/api/admin/backups/{name}").status_code == 403
