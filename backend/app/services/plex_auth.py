"""Connexion Plex via le compte plex.tv (PIN), puis choix du serveur et de la meilleure connexion.

Flux : création d'un PIN -> l'utilisateur se connecte sur app.plex.tv -> le PIN reçoit un jeton
-> liste des serveurs du compte (plex.tv/api/v2/resources) -> test des connexions
(locale, distante, relais) -> enregistrement de l'URL et du jeton du serveur choisi.
"""

import asyncio
from urllib.parse import urlencode

import httpx

from app import __version__
from app.services.errors import ServiceError
from app.services.http import http

PLEX_TV = "https://plex.tv/api/v2"
PRODUCT = "CinéSync"
VERSION = __version__


def _headers(client_id: str, token: str | None = None) -> dict:
    h = {
        "Accept": "application/json",
        # httpx n'accepte que l'ASCII dans les en-têtes : pas d'accent ici
        "X-Plex-Product": "CineSync",
        "X-Plex-Version": VERSION,
        "X-Plex-Client-Identifier": client_id,
        "X-Plex-Device-Name": "CineSync",
        "X-Plex-Platform": "Web",
    }
    if token:
        h["X-Plex-Token"] = token
    return h


async def _call(method: str, url: str, client_id: str, token: str | None = None, **kw) -> httpx.Response:
    try:
        return await http().request(method, url, headers=_headers(client_id, token), timeout=15.0, **kw)
    except httpx.HTTPError as e:
        raise ServiceError("plex", f"plex.tv injoignable : {e.__class__.__name__}") from e


async def create_pin(client_id: str, mode: str = "link", forward_url: str | None = None) -> dict:
    """mode "link" : code court à saisir sur plex.tv/link (fiable partout, y compris sur mobile).
    mode "window" : connexion dans une fenêtre app.plex.tv, qui revient ensuite sur forward_url."""
    params = {"strong": "true"} if mode == "window" else {}
    r = await _call("POST", f"{PLEX_TV}/pins", client_id, params=params)
    if r.status_code >= 400:
        raise ServiceError("plex", f"plex.tv a refusé la création du code ({r.status_code})")
    d = r.json()
    out = {"id": d["id"], "code": d["code"], "expires_in": d.get("expiresIn", 900), "mode": mode}
    if mode == "window":
        q = {"clientID": client_id, "code": d["code"], "context[device][product]": PRODUCT}
        if forward_url:
            q["forwardUrl"] = forward_url
        out["auth_url"] = f"https://app.plex.tv/auth#?{urlencode(q)}"
    else:
        out["link_url"] = "https://plex.tv/link"
    return out


async def check_pin(client_id: str, pin_id: int) -> str | None:
    """Renvoie le jeton du compte une fois la connexion validée, sinon None."""
    r = await _call("GET", f"{PLEX_TV}/pins/{pin_id}", client_id)
    if r.status_code == 404:
        raise ServiceError("plex", "Code de connexion Plex expiré — recommence", 410)
    if r.status_code >= 400:
        raise ServiceError("plex", f"Erreur plex.tv ({r.status_code})")
    return r.json().get("authToken") or None


def _candidates(server: dict) -> list[tuple[int, str, str]]:
    """Connexions candidates (priorité, uri, type). Local d'abord, puis distant, puis relais."""
    out = []
    for c in server.get("connections", []):
        kind = "relay" if c.get("relay") else ("local" if c.get("local") else "remote")
        prio = {"local": 0, "remote": 2, "relay": 4}[kind]
        out.append((prio, c["uri"], kind))
        # Certains routeurs bloquent la résolution *.plex.direct vers une IP privée : on tente aussi l'IP brute
        if kind == "local" and c.get("address") and c.get("port"):
            out.append((prio + 1, f"http://{c['address']}:{c['port']}", "local"))
    return sorted(set(out))


async def _reachable(uri: str, token: str) -> bool:
    try:
        r = await http().get(f"{uri}/identity", headers={"X-Plex-Token": token, "Accept": "application/json"}, timeout=4.0)
        return r.status_code == 200
    except httpx.HTTPError:
        return False


async def best_connection(server: dict) -> dict | None:
    cands = _candidates(server)
    token = server.get("accessToken") or ""
    results = await asyncio.gather(*(_reachable(uri, token) for _, uri, _ in cands))
    for (prio, uri, kind), ok in zip(cands, results):
        if ok:
            return {"uri": uri, "kind": kind}
    return None


async def list_servers(client_id: str, account_token: str, test: bool = True) -> list[dict]:
    r = await _call("GET", f"{PLEX_TV}/resources", client_id, account_token, params={"includeHttps": 1, "includeRelay": 1})
    if r.status_code == 401:
        raise ServiceError("plex", "Session plex.tv expirée — reconnecte-toi", 401)
    if r.status_code >= 400:
        raise ServiceError("plex", f"Erreur plex.tv ({r.status_code})")
    servers = [d for d in r.json() if "server" in (d.get("provides") or "")]
    conns = await asyncio.gather(*(best_connection(s) for s in servers)) if test else [None] * len(servers)
    return [
        {
            "machine_id": s.get("clientIdentifier"),
            "name": s.get("name"),
            "owned": bool(s.get("owned")),
            "online": bool(s.get("presence")),
            "connection": c,
            "_raw": s,
        }
        for s, c in zip(servers, conns)
    ]


def public(servers: list[dict]) -> list[dict]:
    return [{k: v for k, v in s.items() if k != "_raw"} for s in servers]


# --- Comptes (connexion des membres avec Plex) --------------------------------------


async def account_info(client_id: str, token: str) -> dict:
    """Compte plex.tv derrière un jeton : {id, username, title, thumb}."""
    r = await _call("GET", f"{PLEX_TV}/user", client_id, token)
    if r.status_code == 401:
        raise ServiceError("plex", "Session plex.tv expirée — reconnecte-toi", 401)
    if r.status_code >= 400:
        raise ServiceError("plex", f"Erreur plex.tv ({r.status_code})")
    d = r.json()
    return {"id": int(d["id"]), "username": d.get("username") or "", "title": d.get("title") or d.get("username") or "", "thumb": d.get("thumb") or ""}


async def server_access(client_id: str, token: str, machine_id: str) -> dict | None:
    """Accès de ce compte au serveur donné : {token, owned}, ou None s'il n'y a pas accès."""
    for s in await list_servers(client_id, token, test=False):
        if s["machine_id"] == machine_id:
            return {"token": s["_raw"].get("accessToken") or "", "owned": s["owned"]}
    return None


async def server_users(client_id: str, owner_token: str, machine_id: str) -> list[dict]:
    """Comptes Plex avec qui le serveur est partagé (amis et membres du foyer Plex)."""
    import xml.etree.ElementTree as ET

    try:
        r = await http().get("https://plex.tv/api/users", headers={**_headers(client_id, owner_token), "Accept": "application/xml"}, timeout=15.0)
    except httpx.HTTPError as e:
        raise ServiceError("plex", f"plex.tv injoignable : {e.__class__.__name__}") from e
    if r.status_code == 401:
        raise ServiceError("plex", "Session plex.tv expirée — reconnecte le compte Plex de l'admin", 401)
    if r.status_code >= 400:
        raise ServiceError("plex", f"Erreur plex.tv ({r.status_code})")
    try:
        root = ET.fromstring(r.text)
    except ET.ParseError as e:
        raise ServiceError("plex", "Réponse plex.tv illisible") from e
    out = []
    for u in root.iter("User"):
        if not any(s.get("machineIdentifier") == machine_id for s in u.iter("Server")):
            continue
        try:
            uid = int(u.get("id", ""))
        except ValueError:
            continue
        out.append({
            "id": uid,
            "username": u.get("username") or "",
            "title": u.get("title") or u.get("username") or "",
            "thumb": u.get("thumb") or "",
            "home": u.get("home") == "1",
        })
    return out
