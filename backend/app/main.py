import logging
from contextlib import asynccontextmanager

from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse

from app import __version__
from app.config import config
from app.database import init_db
from app.routers import admin, auth, cinema, episodes, justwatch, letterboxd, library, media, news, notifications, plex, requests, search, seerr, swipe, tmdb, tonight, trakt, user
from app.scheduler import start_scheduler, stop_scheduler
from app.services.auth import require_ready
from app.services.errors import ServiceError
from app.services.http import close_http

logging.basicConfig(level=config.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    start_scheduler()
    yield
    stop_scheduler()
    await close_http()


app = FastAPI(
    title="CinéSync",
    version=__version__,
    lifespan=lifespan,
    docs_url="/api/docs" if config.api_docs else None,
    openapi_url="/api/openapi.json" if config.api_docs else None,
    redoc_url=None,
)

app.add_middleware(GZipMiddleware, minimum_size=1024)
if config.cors_list:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.exception_handler(ServiceError)
async def service_error_handler(_: Request, exc: ServiceError):
    return JSONResponse(status_code=exc.status, content={"detail": exc.message, "service": exc.service})


UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}

# Sources autorisées : uniquement CinéSync, sauf les images (affiches, logos : https) et les bandes-annonces
# YouTube (sans cookies). Le service worker télécharge lui-même les affiches TMDB (connect-src).
CSP = "; ".join([
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob: https:",
    "font-src 'self'",
    "connect-src 'self' https://image.tmdb.org",
    "frame-src https://www.youtube-nocookie.com",
    "worker-src 'self'",
    "manifest-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
])

SECURITY_HEADERS = {
    "Content-Security-Policy": CSP,
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
    "Cross-Origin-Opener-Policy": "same-origin",
}
# HSTS : seulement sur le nom de domaine public (PUBLIC_URL). Envoyé via une autre adresse (Tailscale, IP),
# il forcerait le HTTPS pour tous les services de cette machine (interface d'Unraid…).
HSTS_HOST = (urlsplit(config.public_url).hostname or "").lower() if config.hsts_seconds > 0 and config.public_url.startswith("https://") else ""


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    for k, v in SECURITY_HEADERS.items():
        response.headers.setdefault(k, v)
    if HSTS_HOST:
        host = (request.headers.get("x-forwarded-host") or request.headers.get("host") or "").split(",")[0].strip().split(":")[0].lower()
        if host == HSTS_HOST:
            response.headers.setdefault("Strict-Transport-Security", f"max-age={config.hsts_seconds}")
    return response


PUBLIC_HOST = (urlsplit(config.public_url).hostname or "").lower() if config.public_url.startswith("https://") else ""


def _request_host(request: Request) -> str:
    return (request.headers.get("x-forwarded-host") or request.headers.get("host") or "").split(",")[0].strip().split(":")[0].lower()


@app.middleware("http")
async def https_only_on_public_domain(request: Request, call_next):
    """Sur le domaine public (PUBLIC_URL en https), toute visite arrivée en HTTP est renvoyée vers HTTPS,
    même si le proxy ne le fait pas : un mot de passe ne doit jamais circuler en clair."""
    # Si le proxy n'est pas dans FORWARDED_ALLOW_IPS, uvicorn ignore son X-Forwarded-Proto : le schéma reste
    # « http » même en HTTPS. On ne redirige donc que si le proxy n'annonce pas lui-même du HTTPS (pas de boucle).
    forwarded = request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower()
    if PUBLIC_HOST and request.url.scheme == "http" and forwarded != "https" and _request_host(request) == PUBLIC_HOST:
        target = f"https://{PUBLIC_HOST}{request.url.path}" + (f"?{request.url.query}" if request.url.query else "")
        return RedirectResponse(target, status_code=308)
    return await call_next(request)


def _origin(url: str) -> str:
    u = urlsplit(url)
    return f"{u.scheme}://{u.netloc}".lower() if u.scheme and u.netloc else ""


@app.middleware("http")
async def same_origin_only(request: Request, call_next):
    """Protection CSRF : une requête qui modifie des données doit venir de CinéSync lui-même — même
    protocole, même nom et même port (les autres applis d'un serveur partagent souvent le nom de machine).
    En plus du cookie SameSite=Lax. Les navigateurs envoient toujours Origin sur ces requêtes."""
    if request.method in UNSAFE and request.url.path.startswith("/api/"):
        origin = request.headers.get("origin")
        if origin:
            host = (request.headers.get("x-forwarded-host") or request.headers.get("host") or "").split(",")[0].strip()
            allowed = {f"{request.url.scheme}://{host}".lower()} | {_origin(o) for o in config.cors_list}
            if config.public_url:
                allowed.add(_origin(config.public_url))
            if origin.lower() not in allowed:
                return JSONResponse(status_code=403, content={"detail": "Origine de la requête refusée"})
    return await call_next(request)


app.include_router(auth.router, prefix="/api")
# Tout le reste exige une session (et un mot de passe provisoire déjà changé)
for r in (user, tmdb, media, library, cinema, requests, tonight, episodes, trakt, plex, swipe, search, notifications, letterboxd, seerr, justwatch, news, admin):
    app.include_router(r.router, prefix="/api", dependencies=[Depends(require_ready)])


@app.get("/api/health", tags=["meta"])
def health():
    return {"status": "ok", "version": app.version, "mode": config.cinesync_mode}


# --- Interface (image Docker) : fichiers compilés servis par le même serveur -------------

STATIC = config.static_dir.resolve()
NO_CACHE = {"sw.js", "manifest.json", "index.html", "registerSW.js"}

if (STATIC / "index.html").is_file():

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str):
        if path.startswith("api/"):
            return JSONResponse(status_code=404, content={"detail": "Introuvable"})
        target = (STATIC / path).resolve() if path else STATIC / "index.html"
        # Fichier existant, à l'intérieur du dossier de l'interface uniquement
        if not target.is_file() or not target.is_relative_to(STATIC):
            target = STATIC / "index.html"  # route de l'application (SPA)
        if target.name in NO_CACHE:
            headers = {"Cache-Control": "no-cache"}
        elif target.parent.name == "assets":
            headers = {"Cache-Control": "public, max-age=31536000, immutable"}  # noms avec empreinte
        else:
            headers = {"Cache-Control": "public, max-age=86400"}
        return FileResponse(target, headers=headers)
