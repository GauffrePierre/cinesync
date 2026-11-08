// Cadre de l'application (navigation, recherche, notifications, composants UI partagés),
// messages des hooks et des services, et messages d'erreur statiques renvoyés par le serveur
export default {
  // --- Navigation ---
  Découvrir: 'Discover',
  'À venir': 'Upcoming',
  Bibliothèque: 'Library',
  'Pour ce soir': 'Tonight',
  Watchlist: 'Watchlist',
  Profil: 'Profile',
  'Mode swipe': 'Swipe mode',
  Statistiques: 'Statistics',
  Services: 'Services',
  Cinéma: 'Cinema',
  'Vérification en cours…': 'Checking…',

  // --- Barre haute & recherche ---
  'Rechercher…': 'Search…',
  Rechercher: 'Search',
  'Films, séries, ta bibliothèque…': 'Movies, series, your library…',
  Fermer: 'Close',
  'Tape au moins 2 caractères': 'Type at least 2 characters',
  'Aucun résultat pour « {q} »': 'No results for “{q}”',
  'Dans ta bibliothèque Plex': 'In your Plex library',
  'Dans ta watchlist': 'In your watchlist',

  // --- Notifications ---
  Notifications: 'Notifications',
  'Notifications ({n} non lues)': 'Notifications ({n} unread)',
  '{checked} titre(s) vérifié(s), {created} nouvelle(s) alerte(s)': '{checked} title(s) checked, {created} new alert(s)',
  'Vérifier maintenant': 'Check now',
  'Tout marquer comme lu': 'Mark all as read',
  'Aucune notification.': 'No notifications.',
  'Tu seras prévenu quand un titre de ta watchlist arrive sur une de tes plateformes.':
    "You'll be notified when a title from your watchlist arrives on one of your platforms.",
  Supprimer: 'Delete',

  // --- Composants UI ---
  'Données de démonstration — configure {service} dans le Profil pour voir tes vraies données.':
    'Demo data — set up {service} in your Profile to see your real data.',
  '{n} étoile': '{n} star',
  '{n} étoiles': '{n} stars',

  // --- Actions synchronisées (hooks/useMedia) ---
  'Ajouté à la watchlist': 'Added to watchlist',
  'Retiré de la watchlist': 'Removed from watchlist',
  'Marqué comme vu': 'Marked as watched',
  'Noté {stars}/5': 'Rated {stars}/5',
  'Ajouté à tes coups de cœur': 'Added to your favourites',
  'Retiré des titres vus': 'Removed from watched',
  'Retiré des coups de cœur': 'Removed from favourites',
  'Masqué de tes suggestions': 'Hidden from your suggestions',
  'De nouveau proposé': 'Suggested again',
  '{service} : {error}': '{service}: {error}',
  '{label} — OK sur {ok}, échec {errors}': '{label} — OK on {ok}, failed on {errors}',
  '{label} — échec {errors}': '{label} — failed on {errors}',
  '{label} · {services}': '{label} · {services}',
  '{label} (dans SynCiné)': '{label} (in SynCiné)',

  // --- Services (libellés rendus ailleurs) ---
  'En attente': 'Pending',
  'Envoyée à Seerr': 'Sent to Seerr',
  Refusée: 'Declined',
  Disponible: 'Available',

  // --- Erreurs réseau (services/api) ---
  'Serveur SynCiné injoignable': 'SynCiné server unreachable',
  'Données invalides': 'Invalid data',
  'Erreur {status}': 'Error {status}',

  // --- Messages du serveur : services non configurés (services/errors.py) ---
  "TMDB n'est pas configuré — voir la page Profil": 'TMDB is not configured — see the Profile page',
  "Plex n'est pas configuré — voir la page Profil": 'Plex is not configured — see the Profile page',
  "Trakt n'est pas connecté — voir la page Profil": 'Trakt is not connected — see the Profile page',
  "Seerr n'est pas configuré — voir la page Profil": 'Seerr is not configured — see the Profile page',
  "Letterboxd n'est pas configuré — voir la page Profil": 'Letterboxd is not configured — see the Profile page',
  'JustWatch est désactivé — voir la page Profil': 'JustWatch is disabled — see the Profile page',
  "Connecte-toi d'abord avec ton compte Plex": 'Sign in with your Plex account first',
  'Choisis tes cinémas dans le Profil': 'Choose your cinemas in your Profile',
  "Renseigne d'abord le client ID de ton application Trakt": 'Enter your Trakt app client ID first',

  // --- Messages du serveur : erreurs des services ---
  'Client ID Trakt invalide': 'Invalid Trakt client ID',
  'Session Trakt expirée — reconnecte-toi dans le Profil': 'Trakt session expired — reconnect in your Profile',
  "Limite du compte Trakt atteinte (la watchlist d'un compte gratuit est plafonnée)":
    'Trakt account limit reached (free accounts have a capped watchlist)',
  'Trop de requêtes Trakt, réessaie dans un instant': 'Too many Trakt requests, try again in a moment',
  'Introuvable sur Trakt': 'Not found on Trakt',
  'Titre introuvable sur Trakt': 'Title not found on Trakt',
  'Token Plex invalide': 'Invalid Plex token',
  "Chemin d'image invalide": 'Invalid image path',
  'Image Plex indisponible': 'Plex image unavailable',
  'Serveur introuvable sur ce compte Plex': 'Server not found on this Plex account',
  'Code de connexion Plex expiré — recommence': 'Plex sign-in code expired — start again',
  'Session plex.tv expirée — reconnecte-toi': 'plex.tv session expired — sign in again',
  'Session plex.tv expirée — reconnecte-toi dans le Profil': 'plex.tv session expired — sign in again in your Profile',
  'Titre introuvable dans le catalogue Plex': 'Title not found in the Plex catalogue',
  "L'API JustWatch a changé — repli sur TMDB": 'The JustWatch API has changed — falling back to TMDB',
  'Réponse AlloCiné inattendue — le site a peut-être changé': 'Unexpected AlloCiné response — the site may have changed',
  'Clé API Seerr invalide ou droits insuffisants': 'Invalid Seerr API key or insufficient permissions',
  'Ce titre a déjà été demandé dans Seerr': 'This title has already been requested in Seerr',
  'Clé API TMDB invalide': 'Invalid TMDB API key',
  'Titre introuvable sur TMDB': 'Title not found on TMDB',
  'Trop de requêtes TMDB, réessaie dans un instant': 'Too many TMDB requests, try again in a moment',
  "Letterboxd refuse l'accès au flux RSS depuis ce serveur (403)": 'Letterboxd is blocking RSS feed access from this server (403)',

  // --- Messages du serveur : routes ---
  'period doit être day, week, month ou year': 'period must be day, week, month or year',
  'Demande introuvable': 'Request not found',
  'Notification introuvable': 'Notification not found',
  "Demande enregistrée — l'administrateur la traitera": 'Request saved — the administrator will handle it',
  'Demande envoyée à Seerr': 'Request sent to Seerr',
  'Enregistré dans SynCiné — connecte Trakt ou Plex pour synchroniser': 'Saved in SynCiné — connect Trakt or Plex to sync',
  'Choisis tes plateformes dans le Profil': 'Choose your platforms in your Profile',
  'TMDB doit être configuré': 'TMDB must be configured',
  'Notifications de disponibilité désactivées': 'Availability notifications are disabled',
  'Aucune plateforme active': 'No active platform',

  // --- Messages du serveur : état des services (services/health.py) ---
  'Aucune clé TMDB enregistrée': 'No TMDB key saved',
  'TMDB connecté': 'TMDB connected',
  'URL ou token Plex manquant': 'Plex URL or token missing',
  "Trakt n'est pas connecté": 'Trakt is not connected',
  'URL ou clé API Seerr manquante': 'Seerr URL or API key missing',
  'Seerr connecté': 'Seerr connected',
  "Aucun nom d'utilisateur Letterboxd": 'No Letterboxd username',
  'Aucun cinéma sélectionné': 'No cinema selected',
  '{title} est maintenant disponible sur {platforms}': '{title} is now available on {platforms}',
  'Nouvel épisode de {title} : {code}': 'New episode of {title}: {code}',
  'Nouvel épisode de {title} : {code} · {name}': 'New episode of {title}: {code} · {name}',
  '{service} ne répond plus : {detail}': '{service} is not responding: {detail}',
  '{name} demande « {title} »': '{name} is requesting “{title}”',
  'Ta demande « {title} » a été envoyée à Seerr': 'Your request “{title}” was sent to Seerr',
  'Ta demande « {title} » est disponible sur Plex': 'Your request “{title}” is available on Plex',
  'Ta demande « {title} » a été refusée': 'Your request “{title}” was declined',
  "Plusieurs codes de double authentification incorrects : si ce n'était pas toi, change ton mot de passe.": "Several incorrect two-factor codes: if it wasn't you, change your password.",
  'Notifications activées sur cet appareil': 'Notifications enabled on this device',
}
