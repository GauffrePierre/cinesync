from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/ en dev, /app dans le conteneur
_APP_ROOT = Path(__file__).resolve().parents[1]


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    data_dir: Path = _APP_ROOT / "data"
    # Interface compilée (image Docker) ; absente en développement, où Vite la sert
    static_dir: Path = _APP_ROOT / "static"
    # server : admin + comptes de la famille, écran de connexion.
    # personal : une seule personne, sans écran de connexion (à n'exposer que sur un réseau de confiance)
    cinesync_mode: Literal["server", "personal"] = "server"
    # Documentation interactive de l'API (/api/docs) : désactivée par défaut
    api_docs: bool = False
    # HSTS (forcer HTTPS dans le navigateur), en secondes ; 0 = désactivé.
    # À n'activer que si SynCiné a son propre nom de domaine, servi uniquement en HTTPS
    hsts_seconds: int = 0
    public_url: str = ""
    # Origines supplémentaires autorisées (CORS + vérification d'origine), séparées par des virgules.
    # Vide par défaut : l'interface est servie par SynCiné lui-même (ou relayée par Vite en développement)
    cors_origins: str = ""
    notification_interval_hours: int = 24
    log_level: str = "INFO"

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.data_dir / 'cinesync.db'}"

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


config = Config()
