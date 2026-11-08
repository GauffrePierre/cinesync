"""Téléchargement d'une adresse fournie par un utilisateur (flux RSS personnalisé), sans risque de SSRF.

Une adresse saisie dans CinéSync ne doit jamais permettre d'atteindre le réseau local du serveur
(interface d'Unraid, routeur, autres conteneurs…) : seules les adresses publiques sont autorisées,
à chaque redirection. Taille et durée limitées.
"""

import asyncio
import ipaddress
import socket
from urllib.parse import urljoin, urlsplit

import httpcore
import httpx

from app.services.errors import ServiceError
from app.services.http import USER_AGENT

MAX_BYTES = 3 * 1024 * 1024
MAX_REDIRECTS = 4


def _public(ip: str) -> bool:
    addr = ipaddress.ip_address(ip)
    if addr.version == 6 and addr.ipv4_mapped:
        addr = addr.ipv4_mapped
    return addr.is_global and not addr.is_multicast


async def check_url(url: str) -> str:
    """Vérifie une adresse http(s) dont le nom ne pointe que vers des adresses publiques ; renvoie l'URL."""
    u = urlsplit(url.strip())
    if u.scheme not in ("http", "https") or not u.hostname:
        raise ServiceError("news", "Adresse invalide : elle doit commencer par https://", 422)
    if u.username or u.password:
        raise ServiceError("news", "Adresse invalide", 422)
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(u.hostname, u.port or (443 if u.scheme == "https" else 80), type=socket.SOCK_STREAM)
    except socket.gaierror as e:
        raise ServiceError("news", f"Site introuvable : {u.hostname}", 422) from e
    if not infos or not all(_public(info[4][0]) for info in infos):
        raise ServiceError("news", "Cette adresse pointe vers un réseau privé : refusée", 422)
    return url.strip()


class _PublicOnlyBackend(httpcore.AsyncNetworkBackend):
    """Connexions TCP vers des adresses publiques uniquement, vérifiées AU MOMENT de la connexion.

    Sans ça, un nom de domaine malveillant pourrait pointer vers une adresse publique lors de la
    vérification puis vers le réseau local lors de la connexion (« DNS rebinding »). Le nom est résolu
    une seule fois ici, l'adresse contrôlée, et c'est cette adresse qui est jointe (le certificat TLS
    reste vérifié pour le nom d'origine)."""

    def __init__(self):
        self._inner = httpcore.AnyIOBackend()

    async def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        try:
            infos = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
        except socket.gaierror as e:
            raise httpcore.ConnectError(f"résolution impossible : {host}") from e
        addrs = [info[4][0] for info in infos]
        if not addrs or not all(_public(a) for a in addrs):
            raise httpcore.ConnectError("adresse privée refusée")
        return await self._inner.connect_tcp(addrs[0], port, timeout=timeout, local_address=local_address, socket_options=socket_options)

    async def connect_unix_socket(self, path, timeout=None, socket_options=None):
        raise httpcore.ConnectError("socket local refusé")

    async def sleep(self, seconds: float) -> None:
        await self._inner.sleep(seconds)


def _transport() -> httpx.AsyncHTTPTransport:
    transport = httpx.AsyncHTTPTransport()
    # httpcore 1.x : le pool de connexions utilise ce « backend » réseau pour ouvrir chaque connexion
    transport._pool._network_backend = _PublicOnlyBackend()
    return transport


async def fetch(url: str, timeout: float = 15.0) -> tuple[str, bytes, str]:
    """GET d'une adresse publique, redirections vérifiées une à une. Renvoie (url finale, contenu, content-type)."""
    async with httpx.AsyncClient(transport=_transport(), follow_redirects=False, timeout=timeout, headers={"User-Agent": USER_AGENT}) as client:
        for _ in range(MAX_REDIRECTS + 1):
            await check_url(url)
            try:
                async with client.stream("GET", url) as r:
                    if r.is_redirect and r.headers.get("location"):
                        url = urljoin(url, r.headers["location"])
                        continue
                    if r.status_code >= 400:
                        raise ServiceError("news", f"Le site a répondu {r.status_code}", 502)
                    body = b""
                    async for chunk in r.aiter_bytes():
                        body += chunk
                        if len(body) > MAX_BYTES:
                            raise ServiceError("news", "Réponse trop volumineuse", 502)
                    return str(r.url), body, r.headers.get("content-type", "")
            except httpx.HTTPError as e:
                raise ServiceError("news", f"Site injoignable : {e.__class__.__name__}", 502) from e
    raise ServiceError("news", "Trop de redirections", 502)
