# Démarrer avec la version serveur : administrateur

> Au premier démarrage, un **assistant** te guide en quelques écrans : langue et pays, clé TMDB, plateformes, cinémas, serveur multimédia (Plex, Jellyfin ou Emby) et comptes, notifications. Chaque membre que tu ajoutes a aussi le sien. Tu peux le relancer plus tard (Profil → Apparence → Revoir l’assistant de démarrage).

Tu installes SynCiné pour ta famille : tu configures les services une fois pour tous, puis tu ajoutes les comptes. Compte 20 minutes.

> Prérequis : SynCiné installé avec `CINESYNC_MODE=server` (par défaut) et, si tes proches l'utilisent hors de chez toi, une adresse **HTTPS** renseignée dans `PUBLIC_URL` (voir le [README](../../README.md#accès-https-et-application-mobile)).

## 1. Créer le compte administrateur

Au premier lancement, l'écran **Bienvenue sur SynCiné** demande un **code d'installation**. Il est affiché dans les journaux du conteneur :

```bash
docker logs cinesync 2>&1 | grep "code pour créer"
```

Sur Unraid : icône du conteneur → **Logs**. Saisis le code, choisis ton **identifiant** et ton **mot de passe** (12 caractères ou plus si SynCiné est sur Internet).

## 2. Les services du serveur (partagés par tous)

Ces réglages sont faits **une seule fois, par toi**, dans **Profil → Connexions**. Les membres ne les voient pas et ne peuvent pas les modifier.

| Service | Pourquoi | Comment |
|---|---|---|
| **TMDB** (indispensable) | Fiches, tendances, sorties, disponibilités | Clé gratuite : [themoviedb.org](https://www.themoviedb.org/settings/api) → Paramètres → API, puis **Tester la connexion** |
| **Plex** | Bibliothèque, « Lire sur Plex », connexion des membres avec Plex | **Se connecter avec Plex** → code sur plex.tv/link → choisis ton serveur |
| **Jellyfin / Emby** | Bibliothèque, « Lire », titres vus, connexion des membres avec leur compte Jellyfin ou Emby | **Connexions → + → Jellyfin / Emby** : adresse du serveur vue depuis SynCiné (IP locale, pas `localhost` en Docker), clé API (Jellyfin : Tableau de bord → Clés API ; Emby : Paramètres → Clés API), puis **Relier le serveur**. L'adresse publique (facultative) sert aux liens « Lire » ouverts hors de chez toi |
| **Trakt** (application) | Permet à chacun de relier **son** compte Trakt | Crée une application sur [trakt.tv/oauth/applications](https://trakt.tv/oauth/applications/new) (URL de retour `urn:ietf:wg:oauth:2.0:oob`) et colle son **Client ID**. Chaque membre connecte ensuite son propre compte |
| **Seerr** | Demandes d'ajout à ta bibliothèque | Adresse + clé API (Seerr → Paramètres → Général) |
| **JustWatch** | Liens directs, nouveautés, classements | **Activer JustWatch** |

Tes réglages **personnels** (pays, plateformes, cinémas, ton compte Trakt, Letterboxd, synchronisation) se font comme dans la [version personnelle](version-personnelle.md#4-ton-pays-tes-plateformes-tes-cinémas) : chaque membre a les siens.

## 3. Ajouter les membres de la famille

**Profil → Admin → Comptes** (le menu **Espace admin** y mène aussi).

### Avec leur compte Plex
Pour les personnes avec qui ton serveur Plex est déjà partagé :

1. Section **Comptes Plex du serveur** : la liste s'affiche toute seule.
2. **Autoriser** à côté de la personne. Tu peux cocher :
   - **Demandes envoyées directement à Seerr** : ses demandes partent sans passer par toi ;
   - **Permettre aussi la connexion par identifiant et mot de passe** : un mot de passe provisoire à lui transmettre.
3. Envoie-lui l'adresse de SynCiné : elle se connectera avec **Se connecter avec Plex**. Chacun retrouve ses propres vus et sa progression Plex.

### Avec leur compte Jellyfin ou Emby
Pour les personnes qui ont un compte sur ton serveur Jellyfin ou Emby :

1. Section **Comptes Jellyfin du serveur** (ou Emby) : la liste s'affiche toute seule.
2. **Autoriser** à côté de la personne.
3. Envoie-lui l'adresse de SynCiné : elle se connectera avec **Se connecter avec Jellyfin** (ou Emby), avec son identifiant et son mot de passe habituels, vérifiés par ton serveur. SynCiné ne garde pas ce mot de passe.

Un membre qui a déjà un compte SynCiné peut aussi relier son compte Jellyfin lui-même : **Profil → Connexions → + → Jellyfin / Emby → Relier mon compte**.

### Sans compte Plex
Ces comptes ne voient rien de ton serveur Plex (bibliothèque, nom du serveur, titres vus) et ne peuvent pas faire de demandes d'ajout.

1. Section **Comptes SynCiné → Ajouter**.
2. Choisis un **identifiant** et un **mot de passe provisoire** (bouton **Générer**), coche les options si besoin.
3. Transmets l'adresse, l'identifiant et le mot de passe : il sera changé à la première connexion.

Plus tard, le menu **⋯** d'un compte permet de donner ou renouveler un mot de passe, de rendre administrateur, de désactiver ou de supprimer le compte.

## 4. Les demandes de la famille

Quand un membre demande l'ajout d'un titre :
- s'il a le droit **Demandes envoyées directement à Seerr**, la demande part à Seerr ;
- sinon elle arrive dans **Profil → Admin → Demandes** et tu reçois une notification. Tu peux l'**envoyer à Seerr**, la **marquer disponible** ou la **refuser** : le membre est prévenu.

## 5. Le tableau de bord du serveur multimédia

**Profil → Admin → Serveur** (l'onglet porte le nom de ton serveur : Plex, Jellyfin ou Emby) : lectures en cours (qui regarde quoi, débit, transcodage), bibliothèques avec **Analyser**, statistiques des 30 derniers jours.

Si Plex **et** Jellyfin (ou Emby) sont reliés, un sélecteur en haut permet de passer de l'un à l'autre ; chaque serveur y affiche son nombre de lectures en cours. Pour Jellyfin et Emby, les statistiques comptent la dernière lecture de chaque titre par compte (ces serveurs ne gardent pas d'historique complet).

## 6. Check-list sécurité

- [ ] Mot de passe administrateur long et unique.
- [ ] **Double authentification** activée (Profil → Mon compte → Activer), codes de secours rangés en lieu sûr. Si un membre perd son téléphone : menu **⋯** de son compte → **Réinitialiser la double authentification**.
- [ ] Accès depuis Internet uniquement en **HTTPS** (proxy inverse ou Tailscale), `PUBLIC_URL` renseigné.
- [ ] Sauvegarde automatique activée (**Profil → Admin → Sauvegardes**, active par défaut), et de temps en temps une copie téléchargée rangée hors du serveur : elle contient les jetons des services.
- [ ] Mises à jour : `git pull && docker compose up -d --build`, ou l'image publiée.

---
Les membres trouveront leur propre guide ici : [Membre de la famille](serveur-membre.md).
