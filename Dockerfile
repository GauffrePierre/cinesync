# SynCiné : image unique (interface compilée + serveur FastAPI)

# 1. Interface (React + Vite)
FROM node:22-alpine AS frontend
WORKDIR /src
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# 2. Serveur (FastAPI) qui sert aussi l'interface
FROM python:3.12-slim
ARG VERSION=dev
LABEL org.opencontainers.image.title="SynCiné" \
      org.opencontainers.image.description="Streaming, cinémas, watchlists et recommandations, réunis dans une PWA auto-hébergée" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.licenses="AGPL-3.0-only" \
      org.opencontainers.image.source="https://github.com/GauffrePierre/syncine"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PUID=99 \
    PGID=100 \
    FORWARDED_ALLOW_IPS="127.0.0.1,172.16.0.0/12"

WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./app
COPY --from=frontend /src/dist ./static
COPY docker/entrypoint.sh /entrypoint.sh
# Lisible par l'utilisateur non-root qui fait tourner le serveur (quels que soient les droits d'origine)
RUN chmod 755 /entrypoint.sh && chmod -R a+rX /app && mkdir -p /app/data

EXPOSE 8000
VOLUME ["/app/data"]
HEALTHCHECK --interval=60s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)" || exit 1

ENTRYPOINT ["/entrypoint.sh"]
# En-têtes X-Forwarded-* acceptés seulement des proxys de confiance (FORWARDED_ALLOW_IPS, lu par uvicorn) :
# par défaut le serveur lui-même et les réseaux Docker (proxy sur l'hôte, Tailscale serve, NPM en conteneur)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
