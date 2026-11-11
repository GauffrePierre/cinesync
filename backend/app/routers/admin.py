"""Espace administrateur : comptes de la famille, comptes Plex et Jellyfin autorisés, watchlists partagées.
Tableau de bord des serveurs : routers/admin_server.py ; sauvegardes : routers/admin_backups.py."""

import asyncio
import json
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import delete, select, update

from app.database import UserScoped
from app.models import AuthSession, MediaState, Notification, User, UserSettings, WatchEvent
from app.services import auth, messages, plex_auth
from app.services.auth import require_admin, require_server_mode
from app.services.context import SHARED_ID, Ctx, get_ctx, settings_for
from app.services.errors import NotConfigured, ServiceError
from app.services.history import OWNER_ACCOUNT, assign_plex_events

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])

# --- Comptes ---------------------------------------------------------------------------


class UserCreate(BaseModel):
    username: str = Field(max_length=40)
    password: str = Field(max_length=256)
    display_name: str = Field("", max_length=60)
    role: Literal["admin", "member"] = "member"
    can_request_direct: bool = False


class UserUpdate(BaseModel):
    display_name: str | None = Field(None, max_length=60)
    role: Literal["admin", "member"] | None = None
    active: bool | None = None
    can_request_direct: bool | None = None
    jellyfin_login: bool | None = None  # connexion avec le compte Jellyfin / Emby relié
    password: str | None = Field(None, max_length=256)  # nouveau mot de passe provisoire
    reset_two_factor: bool | None = None  # téléphone perdu : désactive la 2FA du compte


class PlexAllow(BaseModel):
    plex_user_id: int
    display_name: str = Field("", max_length=60)
    can_request_direct: bool = False
    # Facultatif : permet aussi la connexion par identifiant + mot de passe (provisoire, à changer)
    password: str | None = Field(None, max_length=256)


def _user(ctx: Ctx, user_id: int) -> User:
    u = ctx.db.get(User, user_id)
    if u is None:
        raise HTTPException(404, "Compte introuvable")
    return u


def _other_admins(ctx: Ctx, user_id: int) -> int:
    return ctx.db.query(User).filter(User.role == "admin", User.active.is_(True), User.id != user_id).count()


def _unique_username(ctx: Ctx, base: str) -> str:
    base = "".join(c for c in base.lower() if c.isalnum() or c in "._-")[:30] or "plex"
    name, n = base, 2
    while ctx.db.query(User).filter(User.username == name).first():
        name, n = f"{base}{n}", n + 1
    return name


@router.get("/users")
def list_users(ctx: Ctx = Depends(get_ctx)):
    users = ctx.db.query(User).order_by(User.role != "admin", User.id).all()
    jf = {st.id: st.jellyfin_username for st in ctx.db.query(UserSettings).filter(UserSettings.jellyfin_user_id != "")}
    return {"results": [{**u.to_dict(), "jellyfin": jf.get(u.id) or None} for u in users]}


@router.post("/users", dependencies=[Depends(require_server_mode)])
def create_user(body: UserCreate, ctx: Ctx = Depends(get_ctx)):
    """Compte local : l'admin choisit identifiant et mot de passe provisoire, changé à la première connexion."""
    username = auth.normalize_username(body.username)
    auth.validate_password(body.password)
    if ctx.db.query(User).filter(User.username == username).first():
        raise HTTPException(409, "Cet identifiant est déjà pris")
    u = User(
        username=username, display_name=body.display_name.strip(), role=body.role, can_request_direct=body.can_request_direct,
        password_hash=auth.hash_password(body.password), must_change_password=True, temp_password_until=auth.temp_password_deadline(),
    )
    ctx.db.add(u)
    ctx.db.flush()
    ctx.db.add(UserSettings(id=u.id, country_code=ctx.settings.country_code, language=ctx.settings.language, onboarding="pending"))
    ctx.db.commit()
    return u.to_dict()


@router.patch("/users/{user_id}")
def update_user(user_id: int, body: UserUpdate, request: Request, ctx: Ctx = Depends(get_ctx)):
    u = _user(ctx, user_id)
    if u.id == ctx.user.id and (body.role == "member" or body.active is False):
        raise HTTPException(409, "Tu ne peux pas retirer tes propres droits d'administrateur")
    if u.id == ctx.user.id and (body.password or body.reset_two_factor):
        # Son propre compte : passer par le Profil (mot de passe actuel ou code exigés)
        raise HTTPException(409, "Pour ton propre compte, utilise Profil → Mon compte")
    if u.id == SHARED_ID and (body.role == "member" or body.active is False):
        raise HTTPException(409, "Le compte administrateur principal porte les réglages du serveur")
    if u.id == SHARED_ID and ctx.user.id != SHARED_ID and (body.password or body.reset_two_factor or body.jellyfin_login is not None):
        # Sinon un autre administrateur prendrait le compte principal (nouveau mot de passe, 2FA retirée) et, avec lui,
        # tout ce que ce compte est seul à pouvoir faire
        raise HTTPException(403, "Réservé à l'administrateur principal")
    if u.is_admin and (body.role == "member" or body.active is False) and _other_admins(ctx, u.id) == 0:
        raise HTTPException(409, "Il faut garder au moins un administrateur")
    if body.display_name is not None:
        u.display_name = body.display_name.strip()
    if body.role is not None:
        u.role = body.role
    if body.can_request_direct is not None:
        u.can_request_direct = body.can_request_direct
    if body.jellyfin_login is not None:
        _set_jellyfin_login(ctx, u, body.jellyfin_login)
    if body.active is not None:
        u.active = body.active
    if body.password:
        auth.validate_password(body.password)
        u.password_hash = auth.hash_password(body.password)
        u.must_change_password = u.id != ctx.user.id
        u.temp_password_until = auth.temp_password_deadline() if u.must_change_password else None
    if body.reset_two_factor:
        u.totp_secret = u.totp_pending = ""
        u.recovery_codes = "[]"
        u.totp_last_counter = u.totp_failures = 0
        u.totp_locked_until = None
    ctx.db.commit()
    if body.active is False or body.password:
        auth.close_all_sessions(ctx.db, u.id, keep_request=request if u.id == ctx.user.id else None)
    return u.to_dict()


@router.delete("/users/{user_id}")
def delete_user(user_id: int, ctx: Ctx = Depends(get_ctx)):
    """Supprime le compte et ses données personnelles (son historique Plex reste celui du serveur)."""
    u = _user(ctx, user_id)
    if u.id == ctx.user.id or u.id == SHARED_ID:
        raise HTTPException(409, "Ce compte ne peut pas être supprimé")
    db = ctx.db
    db.execute(
        update(WatchEvent).where(WatchEvent.user_id == u.id, WatchEvent.source == "plex").values(user_id=0)
        .execution_options(all_users=True, synchronize_session=False)
    )
    # Toutes les tables personnelles, y compris celles ajoutées plus tard : l'id du compte peut être repris par
    # le suivant, qui ne doit hériter de rien (abonnements push, notifications…)
    for model in UserScoped.__subclasses__():
        db.execute(delete(model).where(model.user_id == u.id).execution_options(all_users=True, synchronize_session=False))
    db.query(AuthSession).filter(AuthSession.user_id == u.id).delete()
    if (st := db.get(UserSettings, u.id)) is not None:
        db.delete(st)
    db.delete(u)
    db.commit()
    return {"ok": True}


# --- Comptes Plex autorisés ----------------------------------------------------------


def _plex_admin_ready(ctx: Ctx) -> tuple[str, str, str]:
    s = ctx.settings.shared
    if not (s.plex_account_token and s.plex_machine_id and s.plex_client_id):
        raise NotConfigured("plex", "Connecte d'abord ton compte Plex et choisis ton serveur (Profil)")
    return s.plex_client_id, s.plex_account_token, s.plex_machine_id


@router.get("/plex/accounts", dependencies=[Depends(require_server_mode)])
async def plex_accounts(ctx: Ctx = Depends(get_ctx)):
    """Comptes Plex ayant accès au serveur, et ceux déjà autorisés à se connecter à SynCiné."""
    cid, token, machine = _plex_admin_ready(ctx)
    owner, shared_with = await asyncio.gather(plex_auth.account_info(cid, token), plex_auth.server_users(cid, token, machine))
    linked = {u.plex_user_id: u for u in ctx.db.query(User).filter(User.plex_user_id.isnot(None))}
    accounts = [{**owner, "home": True, "owner": True}] + [{**a, "owner": False} for a in shared_with if a["id"] != owner["id"]]
    for a in accounts:
        u = linked.get(a["id"])
        a["user"] = u.to_dict() if u else None
    return {"results": accounts}


@router.post("/plex/accounts", dependencies=[Depends(require_server_mode)])
async def allow_plex_account(body: PlexAllow, ctx: Ctx = Depends(get_ctx)):
    """Autorise un compte Plex du serveur à se connecter (crée son compte SynCiné)."""
    cid, token, machine = _plex_admin_ready(ctx)
    owner, shared_with = await asyncio.gather(plex_auth.account_info(cid, token), plex_auth.server_users(cid, token, machine))
    if body.plex_user_id == owner["id"]:
        # Le propriétaire du serveur : c'est le compte administrateur principal (celui qui a relié le serveur). Un autre
        # administrateur ne peut pas se l'attribuer : il recevrait sa connexion Plex et son historique
        if ctx.user.id != SHARED_ID:
            raise HTTPException(403, "Réservé à l'administrateur principal")
        ctx.user.plex_user_id, ctx.user.plex_username, ctx.user.plex_thumb = owner["id"], owner["title"], owner["thumb"]
        if ctx.user.plex_server_account_id is None:
            ctx.user.plex_server_account_id = OWNER_ACCOUNT
        ctx.db.commit()
        return ctx.user.to_dict()
    account = next((a for a in shared_with if a["id"] == body.plex_user_id), None)
    if account is None:
        raise HTTPException(404, "Ce compte Plex n'a pas accès à ton serveur")
    existing = ctx.db.query(User).filter(User.plex_user_id == body.plex_user_id).first()
    if existing:
        existing.active = True
        ctx.db.commit()
        return existing.to_dict()
    if body.password:
        auth.validate_password(body.password)
    u = User(
        username=_unique_username(ctx, account["username"] or account["title"]),
        display_name=body.display_name.strip() or account["title"],
        role="member", can_request_direct=body.can_request_direct,
        plex_user_id=account["id"], plex_username=account["title"], plex_thumb=account["thumb"],
        plex_server_account_id=account["id"],
        password_hash=auth.hash_password(body.password) if body.password else "",
        must_change_password=bool(body.password), temp_password_until=auth.temp_password_deadline() if body.password else None,
    )
    ctx.db.add(u)
    ctx.db.flush()
    ctx.db.add(UserSettings(id=u.id, country_code=ctx.settings.country_code, language=ctx.settings.language, onboarding="pending"))
    ctx.db.commit()
    assign_plex_events(ctx.db, account["id"], u.id)  # son historique Plex déjà importé lui revient
    return u.to_dict()


class JellyfinAllow(BaseModel):
    jellyfin_user_id: str = Field(max_length=64)
    display_name: str = Field("", max_length=60)
    can_request_direct: bool = False


@router.post("/jellyfin/accounts", dependencies=[Depends(require_server_mode)])
async def allow_jellyfin_account(body: JellyfinAllow, ctx: Ctx = Depends(get_ctx)):
    """Autorise un compte Jellyfin / Emby du serveur à se connecter (crée son compte SynCiné)."""
    if not ctx.jellyfin_admin:
        raise HTTPException(409, "Serveur Jellyfin non relié")
    account = next((u for u in await ctx.jellyfin_admin.users() if u["id"] == body.jellyfin_user_id and not u["disabled"]), None)
    if account is None:
        raise HTTPException(404, "Compte Jellyfin introuvable sur le serveur")
    existing = ctx.db.query(UserSettings).filter(UserSettings.jellyfin_user_id == account["id"]).first()
    if existing:
        u = ctx.db.get(User, existing.id)
        u.active = True
        _set_jellyfin_login(ctx, u, True)
        ctx.db.commit()
        return u.to_dict()
    u = User(username=_unique_username(ctx, account["name"]), display_name=body.display_name.strip() or account["name"],
             role="member", can_request_direct=body.can_request_direct, jellyfin_login=True)
    ctx.db.add(u)
    ctx.db.flush()
    ctx.db.add(UserSettings(id=u.id, country_code=ctx.settings.country_code, language=ctx.settings.language, onboarding="pending",
                            jellyfin_user_id=account["id"], jellyfin_username=account["name"]))
    ctx.db.commit()
    return u.to_dict()


def _set_jellyfin_login(ctx: Ctx, u: User, allowed: bool) -> None:
    """Autorise (ou retire) la connexion avec le compte Jellyfin / Emby relié ; le compte est prévenu de l'ajout."""
    st = settings_for(ctx.db, u.id)
    if allowed and not st.own.jellyfin_user_id:
        raise HTTPException(409, "Ce compte n'a pas de compte Jellyfin relié")
    if allowed and not u.jellyfin_login:
        ctx.db.add(Notification(user_id=u.id, kind="service", service="security", **messages.fields(
            "La connexion avec ton compte {server} « {name} » est activée sur SynCiné.",
            server="Emby" if ctx.settings.jellyfin_kind == "emby" else "Jellyfin", name=st.own.jellyfin_username)))
    u.jellyfin_login = allowed
    if allowed:  # (ré)autorisation : lève aussi le blocage après trop de mots de passe Jellyfin faux pour ce compte
        auth.jellyfin_release(st.own.jellyfin_username)


# --- Watchlists partagées par la famille -------------------------------------------------------


@router.get("/watchlists", dependencies=[Depends(require_server_mode)])
async def family_watchlists(ctx: Ctx = Depends(get_ctx)):
    """Titres des watchlists partagées (Profil → Préférences) que la personne ne peut pas regarder : ni sur une de
    ses plateformes, ni dans la bibliothèque du serveur à laquelle elle a accès. Seuls les comptes qui ont choisi de
    partager leur watchlist sont lus, sans rien de leur état personnel (vu, note…). Les titres voulus par plusieurs
    personnes sont regroupés en tête."""
    from app.services.enrich import plex_keys, stream_providers

    sharing = set(ctx.db.execute(select(UserSettings.id).where(UserSettings.share_watchlist.is_(True))).scalars())
    others = ctx.db.query(User).filter(User.active.is_(True), User.id != ctx.user.id).all()
    members = {u.id: u for u in others if u.id in sharing}
    rows = ctx.db.execute(
        select(MediaState).where(MediaState.user_id.in_(members)).execution_options(all_users=True)
    ).scalars().all() if members else []
    rows = [r for r in rows if r.in_watchlist]
    index = await plex_keys(ctx)  # bibliothèque du serveur
    # Contexte de chaque personne (sans requête) : ses plateformes, son pays, son accès au serveur
    access = {}
    for uid, u in members.items():
        mctx = Ctx(db=ctx.db, settings=settings_for(ctx.db, uid), user=u)
        access[uid] = (mctx, set(mctx.platforms), mctx.media is not None)

    # Disponibilités jamais vérifiées : demandées pour le pays de la personne (pas enregistrées dans son compte)
    providers = {r.id: json.loads(r.providers or "[]") for r in rows}
    unknown = [r for r in rows if r.providers_checked_at is None][:150]
    sem = asyncio.Semaphore(10)

    async def fill(r: MediaState):
        mctx = access[r.user_id][0]
        if mctx.tmdb.is_mock:
            return
        async with sem:
            try:
                providers[r.id] = stream_providers(await mctx.tmdb.providers(r.media_type, r.tmdb_id))
            except ServiceError:
                pass

    await asyncio.gather(*(fill(r) for r in unknown))

    per_member: dict[int, list[dict]] = {uid: [] for uid in members}
    totals = {uid: 0 for uid in members}
    wanted: dict[tuple[str, int], dict] = {}
    for r in rows:
        _, platforms, has_media = access[r.user_id]
        key = (r.media_type, r.tmdb_id)
        totals[r.user_id] += 1
        on_platform = any(p.get("id") in platforms for p in providers.get(r.id, []))
        if on_platform or (has_media and key in index):
            continue  # la personne peut déjà le regarder
        hit = index.get(key)
        item = {"id": r.tmdb_id, "media_type": r.media_type, "title": r.title, "year": r.year, "poster": r.poster,
                "release_date": r.release_date, "vote_average": r.tmdb_rating, "added": r.listed_at,
                "in_plex": hit is not None, "plex_url": hit.get("plex_url") if hit else None}
        per_member[r.user_id].append(item)
        w = wanted.setdefault(key, {**item, "members": []})
        w["members"].append(members[r.user_id].name)
    # Affiche ou titre pas encore connus (ajout récent, avant la synchronisation) : complétés pour l'affichage seulement
    lacking = {(i["media_type"], i["id"]) for items in per_member.values() for i in items if not i["poster"] or not i["title"]}
    if lacking and not ctx.tmdb.is_mock:
        found: dict[tuple[str, int], dict] = {}

        async def basic(key):
            async with sem:
                try:
                    found[key] = await ctx.tmdb.basic(*key) or {}
                except ServiceError:
                    pass

        await asyncio.gather(*(basic(k) for k in list(lacking)[:100]))
        for i in [i for items in per_member.values() for i in items] + list(wanted.values()):
            b = found.get((i["media_type"], i["id"])) or {}
            i["poster"], i["title"], i["year"] = i["poster"] or b.get("poster"), i["title"] or b.get("title"), i["year"] or b.get("year")
    for items in per_member.values():
        items.sort(key=lambda i: i["added"] or "", reverse=True)
    shared = sorted((w for w in wanted.values() if len(w["members"]) > 1), key=lambda w: (-len(w["members"]), w["title"] or ""))
    return {
        "media_server": ctx.media is not None,
        "members": [
            {"id": uid, "name": u.name, "count": totals[uid], "unavailable": len(per_member[uid]), "items": per_member[uid]}
            for uid, u in sorted(members.items(), key=lambda kv: kv[1].name.lower())
        ],
        "shared": shared,  # hors de portée de plusieurs personnes
        "not_sharing": len(others) - len(members),  # comptes qui ne partagent pas (nombre seulement)
    }
