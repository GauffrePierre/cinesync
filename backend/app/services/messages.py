"""Textes des notifications, dans la langue de chaque compte.

Le gabarit français sert de clé : il est stocké avec la notification (msg_key + msg_params). L'interface le
traduit comme ses autres textes (dictionnaires frontend/src/i18n/en), et les notifications push, écrites
par le serveur, utilisent la version anglaise ci-dessous. Un test vérifie que les deux restent alignés.
"""

import json

TEMPLATES: dict[str, str] = {
    "{title} est maintenant disponible sur {platforms}": "{title} is now available on {platforms}",
    "Nouvel épisode de {title} : {code}": "New episode of {title}: {code}",
    "Nouvel épisode de {title} : {code} · {name}": "New episode of {title}: {code} · {name}",
    "Nouvel épisode de {title} sur {platforms} : {code}": "New episode of {title} on {platforms}: {code}",
    "{service} ne répond plus : {detail}": "{service} is not responding: {detail}",
    "{name} demande « {title} »": "{name} is requesting “{title}”",
    "Ta demande « {title} » a été envoyée à Seerr": "Your request “{title}” was sent to Seerr",
    "Ta demande « {title} » est disponible sur Plex": "Your request “{title}” is available on Plex",
    "Ta demande « {title} » a été refusée": "Your request “{title}” was declined",
    "Plusieurs codes de double authentification incorrects : si ce n'était pas toi, change ton mot de passe.": (
        "Several incorrect two-factor codes: if it wasn't you, change your password."
    ),
    "Notifications activées sur cet appareil": "Notifications enabled on this device",
}


# Autres langues de l'interface (notifications push écrites par le serveur)
TRANSLATIONS: dict[str, dict[str, str]] = {
    "it": {
        "{title} est maintenant disponible sur {platforms}": "{title} è ora disponibile su {platforms}",
        "Nouvel épisode de {title} : {code}": "Nuovo episodio di {title}: {code}",
        "Nouvel épisode de {title} : {code} · {name}": "Nuovo episodio di {title}: {code} · {name}",
        "Nouvel épisode de {title} sur {platforms} : {code}": "Nuovo episodio di {title} su {platforms}: {code}",
        "{service} ne répond plus : {detail}": "{service} non risponde più: {detail}",
        "{name} demande « {title} »": "{name} richiede “{title}”",
        "Ta demande « {title} » a été envoyée à Seerr": "La tua richiesta “{title}” è stata inviata a Seerr",
        "Ta demande « {title} » est disponible sur Plex": "La tua richiesta “{title}” è disponibile su Plex",
        "Ta demande « {title} » a été refusée": "La tua richiesta “{title}” è stata rifiutata",
        "Plusieurs codes de double authentification incorrects : si ce n'était pas toi, change ton mot de passe.": (
            "Diversi codici di autenticazione a due fattori errati: se non eri tu, cambia la password."
        ),
        "Notifications activées sur cet appareil": "Notifiche attivate su questo dispositivo",
    },
    "de": {
        "{title} est maintenant disponible sur {platforms}": "{title} ist jetzt auf {platforms} verfügbar",
        "Nouvel épisode de {title} : {code}": "Neue Folge von {title}: {code}",
        "Nouvel épisode de {title} : {code} · {name}": "Neue Folge von {title}: {code} · {name}",
        "Nouvel épisode de {title} sur {platforms} : {code}": "Neue Folge von {title} auf {platforms}: {code}",
        "{service} ne répond plus : {detail}": "{service} antwortet nicht mehr: {detail}",
        "{name} demande « {title} »": "{name} wünscht sich „{title}“",
        "Ta demande « {title} » a été envoyée à Seerr": "Deine Anfrage „{title}“ wurde an Seerr gesendet",
        "Ta demande « {title} » est disponible sur Plex": "Deine Anfrage „{title}“ ist auf Plex verfügbar",
        "Ta demande « {title} » a été refusée": "Deine Anfrage „{title}“ wurde abgelehnt",
        "Plusieurs codes de double authentification incorrects : si ce n'était pas toi, change ton mot de passe.": (
            "Mehrere falsche Zwei-Faktor-Codes: Wenn du das nicht warst, ändere dein Passwort."
        ),
        "Notifications activées sur cet appareil": "Benachrichtigungen auf diesem Gerät aktiviert",
    },
    "es": {
        "{title} est maintenant disponible sur {platforms}": "{title} ya está disponible en {platforms}",
        "Nouvel épisode de {title} : {code}": "Nuevo episodio de {title}: {code}",
        "Nouvel épisode de {title} : {code} · {name}": "Nuevo episodio de {title}: {code} · {name}",
        "Nouvel épisode de {title} sur {platforms} : {code}": "Nuevo episodio de {title} en {platforms}: {code}",
        "{service} ne répond plus : {detail}": "{service} no responde: {detail}",
        "{name} demande « {title} »": "{name} pide «{title}»",
        "Ta demande « {title} » a été envoyée à Seerr": "Tu petición «{title}» se ha enviado a Seerr",
        "Ta demande « {title} » est disponible sur Plex": "Tu petición «{title}» está disponible en Plex",
        "Ta demande « {title} » a été refusée": "Tu petición «{title}» ha sido rechazada",
        "Plusieurs codes de double authentification incorrects : si ce n'était pas toi, change ton mot de passe.": (
            "Varios códigos de verificación en dos pasos incorrectos: si no fuiste tú, cambia tu contraseña."
        ),
        "Notifications activées sur cet appareil": "Notificaciones activadas en este dispositivo",
    },
}


def render(key: str, params: dict, lang: str = "fr") -> str:
    if lang == "en":
        template = TEMPLATES.get(key, key)
    else:
        template = TRANSLATIONS.get(lang, {}).get(key, key)
    try:
        return template.format(**params)
    except (KeyError, IndexError, ValueError):
        return key


def fields(key: str, **params) -> dict:
    """Colonnes d'une Notification : texte français (repli) + gabarit et paramètres (traduction)."""
    if key not in TEMPLATES:
        raise KeyError(f"Gabarit de notification inconnu : {key}")
    return {"message": key.format(**params), "msg_key": key, "msg_params": json.dumps(params, ensure_ascii=False)}
