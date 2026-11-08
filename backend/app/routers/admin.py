"""Espace administrateur : comptes de la famille, comptes Plex autorisés, tableau de bord du serveur Plex."""

import asyncio
from collections import Counter
from datetime import datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import delete, select, update

from app.database import UserScoped
from app.models import AuthSession, MediaRequest, MediaState, Notification, SwipeHistory, User, UserSettings, WatchEvent
from app.services import auth, plex_auth
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
    password: str | None = Field(None, max_length=256)  # nouveau mot de passe provisoire


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
    return {"results": [u.to_dict() for u in users]}


@router.post("/users", dependencies=[Depends(require_server_mode)])
def create_user(body: UserCreate, ctx: Ctx = Depends(get_ctx)):
    """Compte local : l'admin choisit identifiant et mot de passe provisoire, changé à la première connexion."""
    username = auth.normalize_username(body.username)
    auth.validate_password(body.password)
    if ctx.db.query(User).filter(User.username == username).first():
        raise HTTPException(409, "Cet identifiant est déjà pris")
    u = User(
        username=username, display_name=body.display_name.strip(), role=body.role, can_request_direct=body.can_request_direct,
        password_hash=auth.hash_password(body.password), must_change_password=True,
    )
    ctx.db.add(u)
    ctx.db.flush()
    ctx.db.add(UserSettings(id=u.id, country_code=ctx.settings.country_code, language=ctx.settings.language))
    ctx.db.commit()
    return u.to_dict()


@router.patch("/users/{user_id}")
def update_user(user_id: int, body: UserUpdate, request: Request, ctx: Ctx = Depends(get_ctx)):
    u = _user(ctx, user_id)
    if u.id == ctx.user.id and (body.role == "member" or body.active is False):
        raise HTTPException(409, "Tu ne peux pas retirer tes propres droits d'administrateur")
    if u.id == SHARED_ID and body.role == "member":
        raise HTTPException(409, "Le compte administrateur principal porte les réglages du serveur")
    if u.is_admin and (body.role == "member" or body.active is False) and _other_admins(ctx, u.id) == 0:
        raise HTTPException(409, "Il faut garder au moins un administrateur")
    if body.display_name is not None:
        u.display_name = body.display_name.strip()
    if body.role is not None:
        u.role = body.role
    if body.can_request_direct is not None:
        u.can_request_direct = body.can_request_direct
    if body.active is not None:
        u.active = body.active
    if body.password:
        auth.validate_password(body.password)
        u.password_hash = auth.hash_password(body.password)
        u.must_change_password = u.id != ctx.user.id
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
    for model in (MediaState, SwipeHistory, Notification, MediaRequest, WatchEvent):
        assert issubclass(model, UserScoped)
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
    """Comptes Plex ayant accès au serveur, et ceux déjà autorisés à se connecter à CinéSync."""
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
    """Autorise un compte Plex du serveur à se connecter (crée son compte CinéSync)."""
    cid, token, machine = _plex_admin_ready(ctx)
    owner, shared_with = await asyncio.gather(plex_auth.account_info(cid, token), plex_auth.server_users(cid, token, machine))
    if body.plex_user_id == owner["id"]:
        # Le propriétaire du serveur : c'est le compte de l'admin qui fait la demande
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
        must_change_password=bool(body.password),
    )
    ctx.db.add(u)
    ctx.db.flush()
    ctx.db.add(UserSettings(id=u.id, country_code=ctx.settings.country_code, language=ctx.settings.language))
    ctx.db.commit()
    assign_plex_events(ctx.db, account["id"], u.id)  # son historique Plex déjà importé lui revient
    return u.to_dict()


# --- Tableau de bord du serveur Plex ----------------------------------------------------


def _plex(ctx: Ctx):
    if not ctx.plex_admin:
        raise NotConfigured("plex")
    return ctx.plex_admin


def _decision(value: str | None) -> str:
    """Décision Plex -> direct (lecture directe), copy (flux direct : remuxé sans réencodage) ou transcode."""
    return {"transcode": "transcode", "copy": "copy"}.get(value or "", "direct")


def _mbps(kbps) -> float | None:
    try:
        return round(float(kbps) / 1000, 1) if kbps else None
    except (TypeError, ValueError):
        return None


def _session(m: dict) -> dict:
    kind = m.get("type")
    title = m.get("grandparentTitle") if kind == "episode" else m.get("title")
    detail = f"S{m.get('parentIndex', 0):02d}E{m.get('index', 0):02d} · {m.get('title') or ''}" if kind == "episode" else (str(m.get("year") or ""))
    duration, offset = m.get("duration") or 0, m.get("viewOffset") or 0
    player, user = m.get("Player") or {}, m.get("User") or {}
    session = m.get("Session") or {}
    tc = m.get("TranscodeSession") or {}
    media = next((x for x in m.get("Media") or [] if x.get("selected")), None) or (m.get("Media") or [{}])[0]
    part = (media.get("Part") or [{}])[0]
    video = _decision(tc.get("videoDecision") if tc else part.get("decision"))
    audio = _decision(tc.get("audioDecision") if tc else part.get("decision"))
    overall = "transcode" if "transcode" in (video, audio) else ("copy" if "copy" in (video, audio) else "direct")
    thumb = m.get("grandparentThumb") if kind == "episode" else m.get("thumb")
    resolution = media.get("videoResolution")
    return {
        "id": session.get("id") or m.get("sessionKey"),
        "type": kind,
        "title": title or "",
        "detail": detail,
        "user": user.get("title") or "",
        "user_thumb": user.get("thumb"),
        "player": player.get("title") or player.get("product") or "",
        "platform": player.get("platform") or "",
        "state": player.get("state") or "",
        "local": bool(player.get("local")) or session.get("location") == "lan",
        "progress": round(offset / duration * 100) if duration else None,
        "remaining_min": round((duration - offset) / 60000) if duration else None,
        "thumb": f"/api/plex/image?path={thumb}&width=200" if thumb else None,
        # Débit réellement utilisé par ce flux (bande passante de la session), et celui du fichier d'origine
        "bandwidth_mbps": _mbps(session.get("bandwidth")),
        "source_mbps": _mbps(media.get("bitrate")),
        "quality": f"{resolution}p" if resolution and resolution.isdigit() else (resolution.upper() if resolution else None),
        "transcode": overall,
        "video": video,
        "audio": audio,
        "transcoding": {
            "active": bool(tc) and overall == "transcode",
            "hardware": bool(tc.get("transcodeHwRequested") or tc.get("transcodeHwFullPipeline")),
            "speed": round(float(tc["speed"]), 1) if tc.get("speed") not in (None, "") else None,
            "throttled": bool(tc.get("throttled")),
            "video_codec": f"{(tc.get('sourceVideoCodec') or '').upper()} → {(tc.get('videoCodec') or '').upper()}" if tc.get("videoDecision") == "transcode" else None,
        } if tc else None,
    }


def _totals(sessions: list[dict]) -> dict:
    return {
        "streams": len(sessions),
        "transcodes": sum(1 for s in sessions if s["transcode"] == "transcode"),
        "bandwidth_mbps": round(sum(s["bandwidth_mbps"] or 0 for s in sessions), 1),
        "remote_mbps": round(sum(s["bandwidth_mbps"] or 0 for s in sessions if not s["local"]), 1),
    }


@router.get("/plex/dashboard")
async def plex_dashboard(ctx: Ctx = Depends(get_ctx)):
    """Lectures en cours, bibliothèques (nombre de titres, analyse en cours) et état du serveur."""
    p = _plex(ctx)

    async def safe(coro, default):
        try:
            return await coro
        except ServiceError:
            return default

    root, sessions, sections, activities = await asyncio.gather(
        safe(p._get("/"), {}), safe(p._get("/status/sessions"), {}), safe(p._get("/library/sections"), {}), safe(p._get("/activities"), {})
    )
    if not root:
        raise ServiceError("plex", "Serveur Plex injoignable", 502)

    libs = [d for d in sections.get("Directory", []) or []]

    async def count(d):
        mc = await safe(p._get(f"/library/sections/{d['key']}/all", **{"X-Plex-Container-Start": 0, "X-Plex-Container-Size": 0}), {})
        return mc.get("totalSize", mc.get("size"))

    counts = await asyncio.gather(*(count(d) for d in libs))
    running = [a for a in activities.get("Activity", []) or []]
    scanning = {str(a.get("Context", {}).get("librarySectionID")) for a in running if a.get("type", "").startswith("library")}
    return {
        "server": {
            "name": root.get("friendlyName") or ctx.settings.plex_server_name,
            "version": root.get("version"),
            "platform": " ".join(x for x in (root.get("platform"), root.get("platformVersion")) if x),
            "transcoder": bool(root.get("transcoderVideo")),
            "updated_at": root.get("updatedAt"),
        },
        "sessions": (parsed := [_session(m) for m in sessions.get("Metadata", []) or []]),
        "totals": _totals(parsed),
        "libraries": [
            {
                "id": d["key"], "title": d.get("title"), "type": d.get("type"), "count": c,
                "scanned_at": d.get("scannedAt"), "refreshing": bool(d.get("refreshing")) or d["key"] in scanning,
            }
            for d, c in zip(libs, counts)
        ],
        "activities": [{"title": a.get("title"), "subtitle": a.get("subtitle"), "progress": a.get("progress")} for a in running],
    }


@router.post("/plex/scan")
async def plex_scan(section_id: str | None = None, ctx: Ctx = Depends(get_ctx)):
    """Lance l'analyse d'une bibliothèque (ou de toutes) pour détecter les nouveaux fichiers."""
    p = _plex(ctx)
    await p._action(f"/library/sections/{section_id}/refresh" if section_id else "/library/sections/all/refresh")
    return {"ok": True}


@router.get("/plex/stats")
def plex_stats(days: int = 30, ctx: Ctx = Depends(get_ctx)):
    """Visionnages sur le serveur (historique Plex importé) : par compte, par jour, titres les plus vus."""
    days = max(1, min(days, 365))
    since = datetime.utcnow() - timedelta(days=days)
    rows = ctx.db.execute(
        select(WatchEvent).where(WatchEvent.source == "plex", WatchEvent.watched_at >= since).execution_options(all_users=True)
    ).scalars().all()
    names = {u.id: u.name for u in ctx.db.query(User).all()}
    by_user = Counter(names.get(r.user_id) or f"Plex #{r.plex_account_id}" for r in rows)
    by_day = Counter(r.watched_at.date().isoformat() for r in rows)
    titles = Counter((r.show_title or r.title) for r in rows if (r.show_title or r.title))
    minutes = sum(r.runtime_min or 0 for r in rows)
    return {
        "days": days,
        "plays": len(rows),
        "hours": round(minutes / 60),
        "movies": sum(1 for r in rows if r.kind == "movie"),
        "episodes": sum(1 for r in rows if r.kind == "episode"),
        "by_user": [{"name": n, "plays": c} for n, c in by_user.most_common()],
        "by_day": [{"date": (since + timedelta(days=i + 1)).date().isoformat(), "plays": by_day.get((since + timedelta(days=i + 1)).date().isoformat(), 0)} for i in range(days)],
        "top": [{"title": t, "plays": c} for t, c in titles.most_common(10)],
    }
