# Démarrer avec la version personnelle

> Au premier démarrage, un **assistant** te guide en quelques écrans : langue et pays, plateformes, cinémas, comptes (Plex, Trakt, Letterboxd) et notifications. Tu peux le passer et le relancer plus tard (Profil → Apparence → Revoir l’assistant de démarrage).

Pour une seule personne : pas de comptes, pas de connexion obligatoire. Compte 10 minutes.

> Prérequis : SynCiné installé avec `CINESYNC_MODE=personal` dans `.env` (voir le [README](../../README.md#installation)).

## 1. Premier lancement

Ouvre l'adresse de SynCiné dans ton navigateur : l'application s'affiche directement, sans écran de connexion.

## 2. Protéger l'accès (recommandé)

Tant qu'aucun mot de passe n'est défini, **toute personne qui ouvre l'adresse entre dans ton SynCiné**. Si l'appli est accessible en dehors de chez toi, protège-la :

1. **Profil → Mon compte → Protéger par un mot de passe**.
2. Choisis un **identifiant** et un **mot de passe** (8 caractères minimum ; 12 ou plus si SynCiné est sur Internet).
3. Cet appareil reste connecté ; les autres afficheront l'écran **Connexion**.

Tu peux revenir à l'accès libre plus tard : **Mon compte → Mot de passe → Retirer la protection par mot de passe**.

## 3. La clé TMDB (indispensable)

Sans elle, SynCiné affiche des données de démonstration.

1. Crée un compte gratuit sur [themoviedb.org](https://www.themoviedb.org/signup), puis va dans **Paramètres → API** et demande une clé (usage personnel).
2. Dans SynCiné : **Profil → Connexions → TMDB**, colle la clé (v3) ou le jeton de lecture (v4), puis **Tester la connexion**.

## 4. Ton pays, tes plateformes, tes cinémas

- **Région & Langue** : ton **pays** (disponibilités et sorties), la **langue des contenus** (titres, résumés) et la **langue de l'interface** (français ou anglais).
- **Plateformes** : coche tes abonnements. Ils servent aux badges, aux filtres, au bouton « Regarder sur… » et aux notifications.
- **Cinémas** : cherche tes salles habituelles (France, Allemagne, Espagne, Turquie, Mexique). Leurs séances apparaissent dans **À venir → Sorties cinéma** et dans Découvrir.

## 5. Tes services (facultatifs)

Ajoute-les depuis **Profil → Connexions**, avec le bouton **+** (« Ajouter un service ») :

| Service | Ce que ça apporte | Comment |
|---|---|---|
| **Trakt** | Watchlist, historique, notes, recommandations | Crée une application sur [trakt.tv/oauth/applications](https://trakt.tv/oauth/applications/new) (URL de retour : `urn:ietf:wg:oauth:2.0:oob`), colle son **Client ID**, puis **Se connecter avec Trakt** et saisis le code sur trakt.tv/activate |
| **Letterboxd** | Ton journal de films | Ton nom d'utilisateur Letterboxd (profil public) |
| **JustWatch** | Liens directs vers chaque plateforme, nouveautés, classements | Coche **Activer JustWatch** (source non officielle) |
| **Plex** | Ta bibliothèque, « Lire sur Plex », historique | **Se connecter avec Plex**, saisis le code sur plex.tv/link ; SynCiné trouve ton serveur |
| **Seerr** | Demander l'ajout d'un titre à ta bibliothèque | Adresse de Seerr + clé API (Seerr → Paramètres → Général) |

## 6. Synchroniser tes listes

**Profil → Synchronisation** :

1. **Synchroniser maintenant** rassemble ta watchlist, tes vus et tes notes depuis Trakt, Plex et Letterboxd.
2. Pour garder Trakt et Plex identiques automatiquement, coche **Synchronisation automatique Trakt ⇄ Plex** : un aperçu montre ce qui va changer avant d'activer.

## 7. Le reste, à ton rythme

- **Notifications** : titre de ta watchlist arrivé sur une de tes plateformes, nouvel épisode, service en panne.
- **Actu Ciné** : choisis tes sources (bouton **Sources**) ; tu peux coller l'adresse de n'importe quel site ou chaîne YouTube.
- **Mode swipe**, **Pour ce soir**, **Statistiques** : à découvrir depuis le menu.

## 8. Installer l'appli sur ton téléphone

L'installation demande une adresse en **HTTPS** (voir le [README](../../README.md#accès-https-et-application-mobile)).

- **iPhone / iPad** : Safari → **Partager → Sur l'écran d'accueil**.
- **Android** : Chrome propose l'installation (ou menu ⋮ → **Installer l'application**).

---
Un souci ? Ouvre une *issue* sur GitHub. Pour une faille de sécurité, voir [SECURITY.md](../../SECURITY.md).
