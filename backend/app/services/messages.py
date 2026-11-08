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


def render(key: str, params: dict, lang: str = "fr") -> str:
    template = TEMPLATES.get(key, key) if lang == "en" else key
    try:
        return template.format(**params)
    except (KeyError, IndexError, ValueError):
        return key


def fields(key: str, **params) -> dict:
    """Colonnes d'une Notification : texte français (repli) + gabarit et paramètres (traduction)."""
    if key not in TEMPLATES:
        raise KeyError(f"Gabarit de notification inconnu : {key}")
    return {"message": key.format(**params), "msg_key": key, "msg_params": json.dumps(params, ensure_ascii=False)}
