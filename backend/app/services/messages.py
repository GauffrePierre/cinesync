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
    'Ta demande « {title} » est disponible sur {server}': 'Your request “{title}” is available on {server}',
    "Ta demande « {title} » a été refusée": "Your request “{title}” was declined",
    "Plusieurs codes de double authentification incorrects : si ce n'était pas toi, change ton mot de passe.": (
        "Several incorrect two-factor codes: if it wasn't you, change your password."
    ),
    "Notifications activées sur cet appareil": "Notifications enabled on this device",
    'Saison {season} de {title} complète : {count} épisodes': 'Season {season} of {title} is complete: {count} episodes',
    'Saison {season} de {title} complète sur {platforms} : {count} épisodes': 'Season {season} of {title} is complete on {platforms}: {count} episodes',
    'Dernier épisode de la saison {season} de {title} : {code}': 'Last episode of season {season} of {title}: {code}',
    'Dernier épisode de la saison {season} de {title} sur {platforms} : {code}': 'Last episode of season {season} of {title} on {platforms}: {code}',
    'Premier épisode de la saison {season} de {title} : {code}': 'First episode of season {season} of {title}: {code}',
    'Premier épisode de la saison {season} de {title} sur {platforms} : {code}': 'First episode of season {season} of {title} on {platforms}: {code}',
    "Le compte {server} « {name} » a été relié à ton compte SynCiné. Si ce n'était pas toi, change ton mot de passe.": "The {server} account “{name}” was linked to your SynCiné account. If it wasn't you, change your password.",
    'La connexion avec ton compte {server} « {name} » est activée sur SynCiné.': 'Signing in with your {server} account “{name}” is now enabled on SynCiné.',
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
        'Ta demande « {title} » est disponible sur {server}': 'La tua richiesta “{title}” è disponibile su {server}',
        "Ta demande « {title} » a été refusée": "La tua richiesta “{title}” è stata rifiutata",
        "Plusieurs codes de double authentification incorrects : si ce n'était pas toi, change ton mot de passe.": (
            "Diversi codici di autenticazione a due fattori errati: se non eri tu, cambia la password."
        ),
        "Notifications activées sur cet appareil": "Notifiche attivate su questo dispositivo",
        "Le compte {server} « {name} » a été relié à ton compte SynCiné. Si ce n'était pas toi, change ton mot de passe.": "L'account {server} “{name}” è stato collegato al tuo account SynCiné. Se non sei stato tu, cambia la password.",
        'La connexion avec ton compte {server} « {name} » est activée sur SynCiné.': "L'accesso con il tuo account {server} “{name}” è ora attivo su SynCiné.",
        'Saison {season} de {title} complète : {count} épisodes': 'Stagione {season} di {title} completa: {count} episodi',
        'Saison {season} de {title} complète sur {platforms} : {count} épisodes': 'Stagione {season} di {title} completa su {platforms}: {count} episodi',
        'Dernier épisode de la saison {season} de {title} : {code}': 'Ultimo episodio della stagione {season} di {title}: {code}',
        'Dernier épisode de la saison {season} de {title} sur {platforms} : {code}': 'Ultimo episodio della stagione {season} di {title} su {platforms}: {code}',
        'Premier épisode de la saison {season} de {title} : {code}': 'Primo episodio della stagione {season} di {title}: {code}',
        'Premier épisode de la saison {season} de {title} sur {platforms} : {code}': 'Primo episodio della stagione {season} di {title} su {platforms}: {code}',
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
        'Ta demande « {title} » est disponible sur {server}': 'Deine Anfrage „{title}“ ist auf {server} verfügbar',
        "Ta demande « {title} » a été refusée": "Deine Anfrage „{title}“ wurde abgelehnt",
        "Plusieurs codes de double authentification incorrects : si ce n'était pas toi, change ton mot de passe.": (
            "Mehrere falsche Zwei-Faktor-Codes: Wenn du das nicht warst, ändere dein Passwort."
        ),
        "Notifications activées sur cet appareil": "Benachrichtigungen auf diesem Gerät aktiviert",
        "Le compte {server} « {name} » a été relié à ton compte SynCiné. Si ce n'était pas toi, change ton mot de passe.": 'Das {server}-Konto „{name}“ wurde mit deinem SynCiné-Konto verbunden. Warst du das nicht, ändere dein Passwort.',
        'La connexion avec ton compte {server} « {name} » est activée sur SynCiné.': 'Die Anmeldung mit deinem {server}-Konto „{name}“ ist jetzt auf SynCiné aktiviert.',
        'Saison {season} de {title} complète : {count} épisodes': 'Staffel {season} von {title} ist komplett: {count} Folgen',
        'Saison {season} de {title} complète sur {platforms} : {count} épisodes': 'Staffel {season} von {title} ist auf {platforms} komplett: {count} Folgen',
        'Dernier épisode de la saison {season} de {title} : {code}': 'Letzte Folge von Staffel {season} von {title}: {code}',
        'Dernier épisode de la saison {season} de {title} sur {platforms} : {code}': 'Letzte Folge von Staffel {season} von {title} auf {platforms}: {code}',
        'Premier épisode de la saison {season} de {title} : {code}': 'Erste Folge von Staffel {season} von {title}: {code}',
        'Premier épisode de la saison {season} de {title} sur {platforms} : {code}': 'Erste Folge von Staffel {season} von {title} auf {platforms}: {code}',
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
        'Ta demande « {title} » est disponible sur {server}': 'Tu petición «{title}» está disponible en {server}',
        "Ta demande « {title} » a été refusée": "Tu petición «{title}» ha sido rechazada",
        "Plusieurs codes de double authentification incorrects : si ce n'était pas toi, change ton mot de passe.": (
            "Varios códigos de verificación en dos pasos incorrectos: si no fuiste tú, cambia tu contraseña."
        ),
        "Notifications activées sur cet appareil": "Notificaciones activadas en este dispositivo",
        "Le compte {server} « {name} » a été relié à ton compte SynCiné. Si ce n'était pas toi, change ton mot de passe.": 'La cuenta de {server} «{name}» se ha vinculado a tu cuenta de SynCiné. Si no has sido tú, cambia tu contraseña.',
        'La connexion avec ton compte {server} « {name} » est activée sur SynCiné.': 'El inicio de sesión con tu cuenta de {server} «{name}» está activado en SynCiné.',
        'Saison {season} de {title} complète : {count} épisodes': 'Temporada {season} de {title} completa: {count} episodios',
        'Saison {season} de {title} complète sur {platforms} : {count} épisodes': 'Temporada {season} de {title} completa en {platforms}: {count} episodios',
        'Dernier épisode de la saison {season} de {title} : {code}': 'Último episodio de la temporada {season} de {title}: {code}',
        'Dernier épisode de la saison {season} de {title} sur {platforms} : {code}': 'Último episodio de la temporada {season} de {title} en {platforms}: {code}',
        'Premier épisode de la saison {season} de {title} : {code}': 'Primer episodio de la temporada {season} de {title}: {code}',
        'Premier épisode de la saison {season} de {title} sur {platforms} : {code}': 'Primer episodio de la temporada {season} de {title} en {platforms}: {code}',
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
