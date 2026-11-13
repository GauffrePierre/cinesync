"""Connexion Plex par code court : le QR code ouvre plex.tv/link avec le code déjà rempli."""

import asyncio

import httpx

from app.services import plex_auth


def _fake_plex(monkeypatch, seen: dict):
    async def call(method, url, client_id, token=None, **kw):
        seen["params"] = kw.get("params")
        return httpx.Response(201, json={"id": 42, "code": "AB12", "expiresIn": 600})

    monkeypatch.setattr(plex_auth, "_call", call)


def test_link_pin_comes_with_a_prefilled_link_and_its_qr(monkeypatch):
    seen = {}
    _fake_plex(monkeypatch, seen)
    pin = asyncio.run(plex_auth.create_pin("client", "link"))
    assert seen["params"] == {}
    assert pin["code"] == "AB12" and pin["link_url"] == "https://plex.tv/link?token=AB12"
    assert pin["qr_svg"].startswith("<svg") and "auth_url" not in pin


def test_window_pin_has_no_qr(monkeypatch):
    seen = {}
    _fake_plex(monkeypatch, seen)
    pin = asyncio.run(plex_auth.create_pin("client", "window", "https://syncine.example/plex-done.html"))
    assert seen["params"] == {"strong": "true"} and "qr_svg" not in pin
    assert pin["auth_url"].startswith("https://app.plex.tv/auth#?")
