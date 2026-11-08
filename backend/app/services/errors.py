class ServiceError(Exception):
    """Erreur d'un service externe, renvoyée proprement au frontend."""

    def __init__(self, service: str, message: str, status: int = 502):
        super().__init__(message)
        self.service = service
        self.message = message
        self.status = status


class NotConfigured(ServiceError):
    def __init__(self, service: str, message: str | None = None):
        labels = {
            "tmdb": "TMDB n'est pas configuré",
            "plex": "Plex n'est pas configuré",
            "trakt": "Trakt n'est pas connecté",
            "seerr": "Seerr n'est pas configuré",
            "letterboxd": "Letterboxd n'est pas configuré",
            "justwatch": "JustWatch est désactivé",
        }
        super().__init__(service, message or f"{labels.get(service, service)} — voir la page Profil", 409)
