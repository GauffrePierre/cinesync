"""Espace administrateur : tableau de bord des serveurs multimédias (Plex, Jellyfin / Emby) — lectures en cours,
bibliothèques, analyse, statistiques de visionnage. Réservé aux administrateurs complets (Ctx.server_admin)."""

import asyncio
from collections import Counter
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select

from app.models import User, UserSettings, WatchEvent
from app.services.auth import require_admin
from app.services.clock import utcnow
from app.services.context import Ctx, get_ctx
from app.services.errors import NotConfigured, ServiceError
from app.services.jellyfin_client import ITEM_ID, LIBRARY_TYPES, folder_id, session_summary

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])

# --- Serveurs multimédias reliés (Plex, Jellyfin / Emby) -------------------------------------


@router.get("/servers")
def media_servers(ctx: Ctx = Depends(get_ctx)):
    """Serveurs dont l'administrateur peut voir le tableau de bord (aucune requête réseau)."""
    s = ctx.settings
    out = []
    if not ctx.server_admin:  # autre administrateur, serveur non partagé par l'administrateur principal
        return {"results": out}
    if ctx.plex_admin:
        out.append({"id": "plex", "kind": "plex", "name": s.plex_server_name or "Plex"})
    if ctx.jellyfin_admin:
        kind = s.jellyfin_kind or "jellyfin"
        out.append({"id": "jellyfin", "kind": kind, "name": s.jellyfin_server_name or kind.capitalize()})
    return {"results": out}


async def _safe(coro, default):
    try:
        return await coro
    except ServiceError:
        return default


def _stats(days: int, since: datetime, rows: list[tuple[str, str, str, datetime, int]], approx: bool = False) -> dict:
    """Statistiques de visionnage : rows = (compte, film|épisode, titre, date, durée en minutes)."""
    by_user = Counter(r[0] for r in rows)
    by_day = Counter(r[3].date().isoformat() for r in rows)
    titles = Counter(r[2] for r in rows if r[2])
    dates = [(since + timedelta(days=i + 1)).date().isoformat() for i in range(days)]
    return {
        "days": days,
        "approx": approx,
        "plays": len(rows),
        "hours": round(sum(r[4] or 0 for r in rows) / 60),
        "movies": sum(1 for r in rows if r[1] == "movie"),
        "episodes": sum(1 for r in rows if r[1] == "episode"),
        "by_user": [{"name": n, "plays": c} for n, c in by_user.most_common()],
        "by_day": [{"date": d, "plays": by_day.get(d, 0)} for d in dates],
        "top": [{"title": t, "plays": c} for t, c in titles.most_common(10)],
    }


# --- Tableau de bord du serveur Plex ----------------------------------------------------


def _server_shared(ctx: Ctx) -> None:
    if not ctx.server_admin:
        raise HTTPException(403, "Réservé à l'administrateur principal")


def _plex(ctx: Ctx):
    _server_shared(ctx)
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
    safe = _safe
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
            "kind": "plex",
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
async def plex_scan(section_id: str | None = Query(None, pattern=r"^\d{1,9}$"), ctx: Ctx = Depends(get_ctx)):
    """Lance l'analyse d'une bibliothèque (ou de toutes) pour détecter les nouveaux fichiers."""
    p = _plex(ctx)
    await p._action(f"/library/sections/{section_id}/refresh" if section_id else "/library/sections/all/refresh")
    return {"ok": True}


@router.get("/plex/stats")
def plex_stats(days: int = 30, ctx: Ctx = Depends(get_ctx)):
    """Visionnages sur le serveur (historique Plex importé) : par compte, par jour, titres les plus vus."""
    _server_shared(ctx)  # visionnages de tous les comptes du serveur
    days = max(1, min(days, 365))
    since = utcnow() - timedelta(days=days)
    rows = ctx.db.execute(
        select(WatchEvent).where(WatchEvent.source == "plex", WatchEvent.watched_at >= since).execution_options(all_users=True)
    ).scalars().all()
    names = {u.id: u.name for u in ctx.db.query(User).all()}
    return _stats(days, since, [
        (names.get(r.user_id) or f"Plex #{r.plex_account_id}", r.kind, r.show_title or r.title or "", r.watched_at, r.runtime_min or 0) for r in rows
    ])


# --- Tableau de bord du serveur Jellyfin / Emby -------------------------------------------


def _jellyfin(ctx: Ctx):
    _server_shared(ctx)
    if not ctx.jellyfin_admin:
        raise NotConfigured("jellyfin")
    return ctx.jellyfin_admin


@router.get("/jellyfin/dashboard")
async def jellyfin_dashboard(ctx: Ctx = Depends(get_ctx)):
    """Lectures en cours, bibliothèques, tâches en cours et état du serveur (mêmes clés que pour Plex)."""
    j = _jellyfin(ctx)
    info, sessions, folders, tasks = await asyncio.gather(
        _safe(j.system_info(), {}), _safe(j.sessions(), []), _safe(j.virtual_folders(), []), _safe(j.running_tasks(), [])
    )
    if not info:
        raise ServiceError(j.kind, f"Serveur {j.label} injoignable", 502)
    counts = await asyncio.gather(*(_safe(j.count(f), None) for f in folders))
    scanning = any(t.get("Key") == "RefreshLibrary" for t in tasks)
    parsed = [session_summary(x) for x in sessions]
    return {
        "server": {
            "kind": j.kind,
            "name": info.get("ServerName") or ctx.settings.jellyfin_server_name,
            "version": info.get("Version"),
            "platform": info.get("OperatingSystemDisplayName") or info.get("OperatingSystem") or "",
        },
        "sessions": parsed,
        "totals": _totals(parsed),
        "libraries": [
            {
                "id": folder_id(f), "title": f.get("Name"), "type": LIBRARY_TYPES.get(f.get("CollectionType") or ""), "count": c,
                "scanned_at": None, "refreshing": scanning or f.get("RefreshStatus") == "Active",
            }
            for f, c in zip(folders, counts)
        ],
        "activities": [
            {"title": t.get("Name"), "subtitle": t.get("Category"),
             "progress": round(t["CurrentProgressPercentage"]) if t.get("CurrentProgressPercentage") is not None else None}
            for t in tasks
        ],
    }


@router.post("/jellyfin/scan")
async def jellyfin_scan(section_id: str | None = None, ctx: Ctx = Depends(get_ctx)):
    """Analyse une bibliothèque (ou toutes) pour détecter les nouveaux fichiers."""
    if section_id is not None and not ITEM_ID.match(section_id):
        raise HTTPException(404, "Bibliothèque introuvable")
    await _jellyfin(ctx).refresh(section_id)
    return {"ok": True}


@router.get("/jellyfin/stats")
async def jellyfin_stats(days: int = 30, ctx: Ctx = Depends(get_ctx)):
    """Visionnages sur le serveur, d'après la dernière lecture de chaque titre par compte (le serveur ne garde
    pas d'historique complet)."""
    j = _jellyfin(ctx)
    days = max(1, min(days, 365))
    since = utcnow() - timedelta(days=days)
    accounts = [u for u in await j.users() if not u["disabled"]]
    linked = {st.jellyfin_user_id: st.id for st in ctx.db.execute(select(UserSettings).where(UserSettings.jellyfin_user_id != "")).scalars()}
    names = {u.id: u.name for u in ctx.db.query(User).all()}
    played = await asyncio.gather(*(_safe(j.played_history(since, user_id=u["id"]), []) for u in accounts))
    rows = [
        (names.get(linked.get(u["id"])) or u["name"], p["kind"], p["show_title"] or p["title"], p["watched_at"], p["runtime_min"] or 0)
        for u, items in zip(accounts, played) for p in items
    ]
    return _stats(days, since, rows, approx=True)
