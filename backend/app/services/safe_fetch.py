"""Téléchargement d'une adresse fournie par un utilisateur (flux RSS personnalisé), sans risque de SSRF.

Une adresse saisie dans SynCiné ne doit jamais permettre d'atteindre le réseau local du serveur
(interface d'Unraid, routeur, autres conteneurs…) : seules les adresses publiques sont autorisées,
à chaque redirection. Taille et durée limitées.
"""

import asyncio
import ipaddress
import socket
import zlib
from urllib.parse import urljoin, urlsplit

import httpcore
import httpx

from app.services.errors import ServiceError
from app.services.http import USER_AGENT

MAX_BYTES = 3 * 1024 * 1024
MAX_REDIRECTS = 4


_NAT64 = ipaddress.ip_network("64:ff9b::/96")
_V4_COMPAT = ipaddress.ip_network("::/96")


def _public(ip: str) -> bool:
    addr = ipaddress.ip_address(ip)
    if addr.version == 6:
        if addr.ipv4_mapped:
            addr = addr.ipv4_mapped
        elif addr in _NAT64 or addr in _V4_COMPAT:  # adresse IPv4 enveloppée (NAT64, ancienne forme ::a.b.c.d)
            addr = ipaddress.IPv4Address(int(addr) & 0xFFFFFFFF)
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
    except socket.gaierror:
        infos = []
    if not infos or not all(_public(info[4][0]) for info in infos):
        # Même message pour un nom inconnu et un nom du réseau local : pas de sondage des noms internes
        raise ServiceError("news", "Site introuvable ou non public : refusé", 422)
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


class _Body:
    """Contenu brut décompressé ici, avec plafond sur la taille DÉCOMPRESSÉE (httpx décompresserait tout
    d'un bloc : une petite réponse gzip, voire « gzip, gzip », pourrait remplir la mémoire)."""

    def __init__(self, encoding: str):
        enc = encoding.strip().lower()
        if enc in ("", "identity"):
            self._z = None
        elif enc in ("gzip", "x-gzip", "deflate"):
            self._z = zlib.decompressobj(47)  # gzip ou zlib, détecté automatiquement
        else:
            raise ServiceError("news", "Encodage de réponse non pris en charge", 502)
        self.data = bytearray()

    def add(self, chunk: bytes) -> None:
        if self._z is None:
            self.data += chunk
        else:
            self.data += self._z.decompress(chunk, MAX_BYTES + 1 - len(self.data))
            if self._z.unconsumed_tail:
                raise ServiceError("news", "Réponse trop volumineuse", 502)
        if len(self.data) > MAX_BYTES:
            raise ServiceError("news", "Réponse trop volumineuse", 502)


async def fetch(url: str, timeout: float = 15.0) -> tuple[str, bytes, str]:
    """GET d'une adresse publique, redirections vérifiées une à une. Renvoie (url finale, contenu, content-type).
    Durée totale plafonnée (un site qui envoie un octet de temps en temps ne retient pas la requête)."""
    try:
        async with asyncio.timeout(timeout * 2):
            return await _fetch(url, timeout)
    except TimeoutError as e:
        raise ServiceError("news", "Le site met trop de temps à répondre", 502) from e


async def _fetch(url: str, timeout: float) -> tuple[str, bytes, str]:
    headers = {"User-Agent": USER_AGENT, "Accept-Encoding": "gzip"}
    async with httpx.AsyncClient(transport=_transport(), follow_redirects=False, timeout=timeout, headers=headers) as client:
        for _ in range(MAX_REDIRECTS + 1):
            await check_url(url)
            try:
                async with client.stream("GET", url) as r:
                    if r.is_redirect and r.headers.get("location"):
                        url = urljoin(url, r.headers["location"])
                        continue
                    if r.status_code >= 400:
                        raise ServiceError("news", f"Le site a répondu {r.status_code}", 502)
                    body = _Body(r.headers.get("content-encoding", ""))
                    async for chunk in r.aiter_raw():
                        body.add(chunk)
                    return str(r.url), bytes(body.data), r.headers.get("content-type", "")
            except httpx.HTTPError as e:
                raise ServiceError("news", f"Site injoignable : {e.__class__.__name__}", 502) from e
    raise ServiceError("news", "Trop de redirections", 502)
