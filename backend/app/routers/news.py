"""Actu Ciné : articles et vidéos des sources choisies par chaque membre."""

import json
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.services import news
from app.services.context import Ctx, get_ctx

router = APIRouter(prefix="/news", tags=["news"])

MAX_SOURCES = 40


class SourceRef(BaseModel):
    id: str = Field(max_length=80)
    name: str = Field("", max_length=120)
    url: str = Field("", max_length=500)
    kind: Literal["site", "youtube"] = "site"
    home: str | None = Field(None, max_length=500)


class SourcesIn(BaseModel):
    sources: list[SourceRef] = Field(max_length=MAX_SOURCES)


class CustomIn(BaseModel):
    url: str = Field(min_length=4, max_length=500)


def _stored(ctx: Ctx) -> list[dict] | None:
    try:
        raw = json.loads(ctx.settings.news_sources or "null")
    except ValueError:
        return None
    return raw if isinstance(raw, list) else None


def active_sources(ctx: Ctx) -> list[dict]:
    """Sources du compte. Celles du catalogue sont toujours relues depuis le catalogue (adresse de confiance)."""
    stored = _stored(ctx)
    if stored is None:
        lang = "en" if (ctx.settings.ui_language or "fr") == "en" else "fr"
        return [news.BY_ID[i] for i in news.DEFAULTS[lang]]
    out = []
    for s in stored:
        if s.get("id") in news.BY_ID:
            out.append(news.BY_ID[s["id"]])
        elif str(s.get("id", "")).startswith(("rss:", "yt:")) and s.get("url"):
            out.append({k: s.get(k) for k in ("id", "name", "url", "kind", "home")})
    return out


def _save(ctx: Ctx, sources: list[dict]) -> None:
    ctx.settings.news_sources = json.dumps(sources[:MAX_SOURCES])
    ctx.db.commit()


@router.get("")
async def feed(kind: Literal["all", "article", "video"] = "all", source: str | None = None, limit: int = 80, ctx: Ctx = Depends(get_ctx)):
    sources = active_sources(ctx)
    if source:
        sources = [s for s in sources if s["id"] == source]
    items, errors = await news.gather(sources, ctx.settings.youtube_api_key)
    if kind != "all":
        items = [i for i in items if i["kind"] == kind]
    return {
        "results": items[: max(1, min(limit, 200))],
        "sources": [{"id": s["id"], "name": s["name"], "kind": s["kind"], "home": s.get("home"), "error": errors.get(s["id"])} for s in active_sources(ctx)],
    }


@router.get("/image")
async def image(u: str, s: str):
    """Image d'un article, relayée et réduite (adresse signée par le serveur, voir services/news.py)."""
    if not news.valid_signature(u, s):
        raise HTTPException(403, "Adresse d'image non signée")
    path = await news.image(u)
    return FileResponse(path, media_type="image/webp", headers={"Cache-Control": "private, max-age=604800"})


@router.get("/catalog")
def catalog(ctx: Ctx = Depends(get_ctx)):
    active = active_sources(ctx)
    return {
        "catalog": [{k: s[k] for k in ("id", "name", "kind", "lang", "home")} for s in news.CATALOG],
        "active": [{k: s.get(k) for k in ("id", "name", "kind", "home", "url")} for s in active],
        "youtube_api": bool(ctx.settings.youtube_api_key),
    }


@router.put("/sources")
def set_sources(body: SourcesIn, ctx: Ctx = Depends(get_ctx)):
    """Liste des sources du compte. Une source personnelle n'est gardée que si elle était déjà connue
    (ajoutée via /custom, donc vérifiée) : on ne peut pas glisser ici une adresse arbitraire."""
    known = {s["id"]: s for s in active_sources(ctx)}
    out = []
    for s in body.sources:
        if s.id in news.BY_ID:
            out.append({"id": s.id})
        elif s.id in known:
            out.append(known[s.id])
    _save(ctx, out)
    return {"active": active_sources(ctx)}


@router.post("/sources/custom")
async def add_custom(body: CustomIn, ctx: Ctx = Depends(get_ctx)):
    """Ajoute un site (flux RSS ou page), ou une chaîne YouTube, après vérification."""
    current = active_sources(ctx)
    if len(current) >= MAX_SOURCES:
        raise HTTPException(409, f"{MAX_SOURCES} sources au maximum")
    source = await news.resolve(body.url, ctx.settings.youtube_api_key)
    if source["id"] not in {s["id"] for s in current}:
        stored = [{"id": s["id"]} if s["id"] in news.BY_ID else s for s in current]
        _save(ctx, stored + [source])
    return {"source": source, "active": active_sources(ctx)}
