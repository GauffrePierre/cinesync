"""Santé des services configurés : tests de connexion, état courant, alertes en cas de panne.

- test_service() : un test de connexion (utilisé par le bouton « Tester » du Profil et par la surveillance).
- check_all() : teste tous les services utilisés ; appelé périodiquement par le scheduler.
- Lorsqu'un service passe de « OK » (ou inconnu) à « en panne », une notification est créée.

Services du serveur (TMDB, Plex, Seerr, JustWatch) : un seul état, alertes aux administrateurs.
Services personnels (Trakt, Letterboxd, cinémas) : un état par compte, alerte au compte concerné.
"""

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from app.models import Notification, User
from app.services.context import SHARED_ID, Ctx
from app.services.errors import ServiceError
from app.services.justwatch_client import JustWatchClient
from app.services.letterboxd_client import LetterboxdClient
from app.services.seerr_client import SeerrClient
from app.services.tmdb_client import TMDBClient

log = logging.getLogger(__name__)

SERVICES = ("tmdb", "plex", "trakt", "seerr", "letterboxd", "justwatch", "cinema")
LABELS = {"tmdb": "TMDB", "plex": "Plex", "trakt": "Trakt", "seerr": "Seerr", "letterboxd": "Letterboxd", "justwatch": "JustWatch", "cinema": "Cinéma (AlloCiné)"}

GLOBAL_SERVICES = ("tmdb", "plex", "seerr", "justwatch")

# État en mémoire : {(0 | id du compte, service): {"ok": bool, "message": str, "checked_at": iso}}
_state: dict[tuple[int, str], dict] = {}


def _key(service: str, user_id: int) -> tuple[int, str]:
    return (0, service) if service in GLOBAL_SERVICES else (user_id, service)


def _plex_token(s) -> str:
    own, shared = getattr(s, "own", s), getattr(s, "shared", s)
    return own.plex_token or shared.plex_token


def used_services(s) -> list[str]:
    """Services que l'utilisateur a effectivement configurés (affichés dans la sidebar)."""
    used = {
        "tmdb": bool(s.tmdb_api_key),
        "plex": bool(s.plex_url and _plex_token(s)),
        "trakt": bool(s.trakt_client_id and s.trakt_access_token),
        "seerr": bool(s.seerr_url and s.seerr_api_key),
        "letterboxd": bool(s.letterboxd_username),
        "justwatch": bool(s.justwatch_enabled),
        "cinema": bool(s.cinema_list),
    }
    return [k for k in SERVICES if used[k]]


async def test_service(ctx: Ctx, service: str) -> dict:
    """{ok, message, details} — ne lève pas d'exception pour une panne de service."""
    s = ctx.settings
    try:
        if service == "tmdb":
            if not s.tmdb_api_key:
                return {"ok": False, "message": "Aucune clé TMDB enregistrée"}
            d = await TMDBClient(s.tmdb_api_key, s.language, s.country_code).test()
            return {"ok": True, "message": "TMDB connecté", "details": d}
        if service == "plex":
            if not ctx.plex:
                return {"ok": False, "message": "URL ou token Plex manquant"}
            d = await ctx.plex.test()
            return {"ok": True, "message": f"Plex connecté — {d['sections']} bibliothèque(s) films/séries", "details": d}
        if service == "trakt":
            if not ctx.trakt:
                return {"ok": False, "message": "Trakt n'est pas connecté"}
            me = await ctx.trakt.me()
            user = me.get("user", {}).get("username")
            return {"ok": True, "message": f"Trakt connecté en tant que {user}", "details": {"username": user}}
        if service == "seerr":
            if not (s.seerr_url and s.seerr_api_key):
                return {"ok": False, "message": "URL ou clé API Seerr manquante"}
            d = await SeerrClient(s.seerr_url, s.seerr_api_key).test()
            return {"ok": True, "message": f"Seerr connecté{' (v' + d['version'] + ')' if d.get('version') else ''}", "details": d}
        if service == "letterboxd":
            if not s.letterboxd_username:
                return {"ok": False, "message": "Aucun nom d'utilisateur Letterboxd"}
            d = await LetterboxdClient(s.letterboxd_username).test()
            return {"ok": True, "message": f"Flux Letterboxd lu — {d['entries']} entrée(s) récente(s)", "details": d}
        if service == "cinema":
            cinemas = s.cinema_list
            if not cinemas:
                return {"ok": False, "message": "Aucun cinéma sélectionné"}
            from datetime import date

            from app.services import allocine_client

            films = await allocine_client.showtimes(cinemas[0]["id"], date.today().isoformat(), cinemas[0].get("country") or "FR")
            return {"ok": True, "message": f"AlloCiné joignable — {len(films)} film(s) aujourd'hui à {cinemas[0]['name']}", "details": {"films": len(films)}}
        if service == "justwatch":
            d = await JustWatchClient(s.country_code, s.language).test()
            return {"ok": True, "message": f"API JustWatch joignable — {d['packages']} plateformes en {s.country_code}", "details": d}
    except ServiceError as e:
        return {"ok": False, "message": e.message}
    except Exception as e:  # filet de sécurité : la surveillance ne doit jamais planter
        log.exception("Test %s", service)
        return {"ok": False, "message": f"Erreur inattendue : {e.__class__.__name__}"}
    raise ValueError(f"Service inconnu : {service}")


def _recipients(db, service: str, user_id: int) -> list[int]:
    """Comptes à prévenir d'une panne (ceux qui n'ont pas coupé ces alertes)."""
    from app.models import UserSettings

    if service in GLOBAL_SERVICES:
        ids = [u.id for u in db.query(User).filter(User.role == "admin", User.active.is_(True))]
    else:
        ids = [user_id]
    return [i for i in ids if (st := db.get(UserSettings, i)) is None or st.notify_services]


def record(db, service: str, result: dict, user_id: int = SHARED_ID) -> None:
    """Met à jour l'état ; crée une notification si le service vient de tomber en panne."""
    key = _key(service, user_id)
    previous = _state.get(key)
    _state[key] = {"ok": result["ok"], "message": result["message"], "checked_at": datetime.now(timezone.utc).isoformat()}
    if result["ok"] or (previous is not None and not previous["ok"]):
        return
    created = False
    for rid in _recipients(db, service, user_id):
        # Pas de doublon si une alerte non lue existe déjà pour ce service (ex. après un redémarrage)
        exists = db.execute(
            select(Notification.id)
            .where(Notification.user_id == rid, Notification.kind == "service", Notification.service == service, Notification.read.is_(False))
            .execution_options(all_users=True)
        ).first()
        if exists:
            continue
        db.add(
            Notification(
                user_id=rid,
                kind="service",
                service=service,
                tmdb_id=0,
                media_type="",
                title=LABELS[service],
                message=f"{LABELS[service]} ne répond plus : {result['message']}",
            )
        )
        created = True
    if created:
        db.commit()
    log.warning("Service %s en panne : %s", service, result["message"])


def forget(service: str, user_id: int = SHARED_ID) -> None:
    _state.pop(_key(service, user_id), None)


def state_for(s, user_id: int = SHARED_ID) -> dict[str, dict | None]:
    """État des services utilisés par ce compte (None = pas encore vérifié)."""
    return {k: _state.get(_key(k, user_id)) for k in used_services(s)}


async def check_one(ctx: Ctx) -> dict:
    """Services personnels du compte ; ceux du serveur une seule fois (compte principal)."""
    used = [k for k in used_services(ctx.settings) if k not in GLOBAL_SERVICES or ctx.user.id == SHARED_ID]
    results = await asyncio.gather(*(test_service(ctx, k) for k in used))
    for k, r in zip(used, results):
        record(ctx.db, k, r, ctx.user.id)
    return {k: r["ok"] for k, r in zip(used, results)}


async def check_all(user_ids: list[int] | None = None) -> dict:
    from app.scheduler import for_each_user

    return await for_each_user(check_one, user_ids)
