"""Tests de bout en bout : un vrai serveur SynCiné (base vide, interface compilée), piloté par Chromium.

Prérequis : l'interface compilée (cd frontend && npm run build), les dépendances du serveur, puis
    pip install -r e2e/requirements.txt && python -m playwright install chromium
Lancer depuis la racine du dépôt : python -m pytest e2e
E2E_PYTHON : Python qui fait tourner le serveur (par défaut, celui des tests).
"""

import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
from playwright.sync_api import Browser, Page, Playwright, expect, sync_playwright

ROOT = Path(__file__).resolve().parent.parent
ADMIN = ("admin", "admin-e2e-pass-123")
expect.set_options(timeout=15_000)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def server(tmp_path_factory):
    """Serveur SynCiné neuf (version serveur, sans clé TMDB : données de démonstration)."""
    dist = ROOT / "frontend" / "dist"
    if not (dist / "index.html").is_file():
        pytest.exit("Interface non compilée : cd frontend && npm run build", 2)
    data = tmp_path_factory.mktemp("data")
    port = _free_port()
    log = data / "server.log"
    env = {**os.environ, "DATA_DIR": str(data), "STATIC_DIR": str(dist), "CINESYNC_MODE": "server", "LOG_LEVEL": "WARNING",
           "PUBLIC_URL": "", "TZ": "Europe/Paris"}
    with open(log, "w") as out:
        proc = subprocess.Popen(
            [os.environ.get("E2E_PYTHON", sys.executable), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
            cwd=ROOT / "backend", env=env, stdout=out, stderr=subprocess.STDOUT,
        )
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(160):
            try:
                if httpx.get(f"{base}/api/health", timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.25)
        else:
            pytest.exit(f"Le serveur ne démarre pas :\n{log.read_text()[-3000:]}", 2)
        code = re.search(r"administrateur -> (\S+)", log.read_text())
        assert code, "code d'installation absent des journaux"
        yield {"base": base, "code": code.group(1), "log": log}
    finally:
        proc.terminate()
        try:
            proc.wait(10)
        except subprocess.TimeoutExpired:
            proc.kill()


@pytest.fixture(scope="session")
def pw() -> Playwright:
    with sync_playwright() as p:
        yield p


@pytest.fixture(scope="session")
def browser(pw) -> Browser:
    b = pw.chromium.launch()
    yield b
    b.close()


def open_page(browser: Browser, server: dict, state=None, device: dict | None = None) -> Page:
    """Nouvel onglet isolé (cookies propres) ; page.errors recueille les erreurs JavaScript non gérées."""
    options = device or {"viewport": {"width": 1280, "height": 900}}
    ctx = browser.new_context(base_url=server["base"], storage_state=state, locale="fr-FR", **options)
    page = ctx.new_page()
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    return page


@pytest.fixture(scope="session")
def admin_state(server, browser, tmp_path_factory) -> Path:
    """Installation par l'interface : code d'installation, compte administrateur, puis assistant passé."""
    page = open_page(browser, server)
    page.goto("/")
    expect(page.get_by_text("Bienvenue sur SynCiné")).to_be_visible()
    page.get_by_placeholder("XXXX-XXXX-XXXX").fill(server["code"])
    page.get_by_label("Identifiant").fill(ADMIN[0])
    page.locator("input[autocomplete=new-password]").nth(0).fill(ADMIN[1])
    page.locator("input[autocomplete=new-password]").nth(1).fill(ADMIN[1])
    page.get_by_role("button", name="Créer le compte administrateur").click()
    # Nouvelle installation : l'assistant de premier démarrage s'ouvre
    page.get_by_role("button", name="Passer l’assistant").click()
    expect(page.get_by_text("Données de démonstration")).to_be_visible()
    assert page.errors == []
    path = tmp_path_factory.mktemp("state") / "admin.json"
    page.context.storage_state(path=str(path))
    page.context.close()
    return path


@pytest.fixture
def admin_page(browser, server, admin_state) -> Page:
    page = open_page(browser, server, state=str(admin_state))
    yield page
    page.context.close()
