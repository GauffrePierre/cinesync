# Démarrer avec la version serveur : administrateur

Tu installes CinéSync pour ta famille : tu configures les services une fois pour tous, puis tu ajoutes les comptes. Compte 20 minutes.

> Prérequis : CinéSync installé avec `CINESYNC_MODE=server` (par défaut) et, si tes proches l'utilisent hors de chez toi, une adresse **HTTPS** renseignée dans `PUBLIC_URL` (voir le [README](../../README.md#accès-https-et-application-mobile)).

## 1. Créer le compte administrateur

Au premier lancement, l'écran **Bienvenue sur CinéSync** demande un **code d'installation**. Il est affiché dans les journaux du conteneur :

```bash
docker logs cinesync 2>&1 | grep "code pour créer"
```

Sur Unraid : icône du conteneur → **Logs**. Saisis le code, choisis ton **identifiant** et ton **mot de passe** (12 caractères ou plus si CinéSync est sur Internet).

## 2. Les services du serveur (partagés par tous)

Ces réglages sont faits **une seule fois, par toi**, dans **Profil → Connexions**. Les membres ne les voient pas et ne peuvent pas les modifier.

| Service | Pourquoi | Comment |
|---|---|---|
| **TMDB** (indispensable) | Fiches, tendances, sorties, disponibilités | Clé gratuite : [themoviedb.org](https://www.themoviedb.org/settings/api) → Paramètres → API, puis **Tester la connexion** |
| **Plex** | Bibliothèque, « Lire sur Plex », connexion des membres avec Plex | **Se connecter avec Plex** → code sur plex.tv/link → choisis ton serveur |
| **Trakt** (application) | Permet à chacun de relier **son** compte Trakt | Crée une application sur [trakt.tv/oauth/applications](https://trakt.tv/oauth/applications/new) (URL de retour `urn:ietf:wg:oauth:2.0:oob`) et colle son **Client ID**. Chaque membre connecte ensuite son propre compte |
| **Seerr** | Demandes d'ajout à ta bibliothèque | Adresse + clé API (Seerr → Paramètres → Général) |
| **JustWatch** | Liens directs, nouveautés, classements | **Activer JustWatch** |

Tes réglages **personnels** (pays, plateformes, cinémas, ton compte Trakt, Letterboxd, synchronisation) se font comme dans la [version personnelle](version-personnelle.md#4-ton-pays-tes-plateformes-tes-cinémas) : chaque membre a les siens.

## 3. Ajouter les membres de la famille

**Profil → Réglages admin → Comptes de la famille** (ou **Espace admin → Utilisateurs**).

### Avec leur compte Plex
Pour les personnes avec qui ton serveur Plex est déjà partagé :

1. Section **Comptes Plex du serveur** : la liste s'affiche toute seule.
2. **Autoriser** à côté de la personne. Tu peux cocher :
   - **Demandes envoyées directement à Seerr** : ses demandes partent sans passer par toi ;
   - **Permettre aussi la connexion par identifiant et mot de passe** : un mot de passe provisoire à lui transmettre.
3. Envoie-lui l'adresse de CinéSync : elle se connectera avec **Se connecter avec Plex**. Chacun retrouve ses propres vus et sa progression Plex.

### Sans compte Plex
Ces comptes ne voient rien de ton serveur Plex (bibliothèque, nom du serveur, titres vus) et ne peuvent pas faire de demandes d'ajout.

1. Section **Comptes CinéSync → Ajouter**.
2. Choisis un **identifiant** et un **mot de passe provisoire** (bouton **Générer**), coche les options si besoin.
3. Transmets l'adresse, l'identifiant et le mot de passe : il sera changé à la première connexion.

Plus tard, le menu **⋯** d'un compte permet de donner ou renouveler un mot de passe, de rendre administrateur, de désactiver ou de supprimer le compte.

## 4. Les demandes de la famille

Quand un membre demande l'ajout d'un titre :
- s'il a le droit **Demandes envoyées directement à Seerr**, la demande part à Seerr ;
- sinon elle arrive dans **Espace admin → Demandes** et tu reçois une notification. Tu peux l'**envoyer à Seerr**, la **marquer disponible** ou la **refuser** : le membre est prévenu.

## 5. Le tableau de bord Plex

**Espace admin → Plex** (ou **Profil → Réglages admin → Serveur Plex**) : lectures en cours (qui regarde quoi, débit, transcodage), bibliothèques avec **Analyser**, statistiques des 30 derniers jours.

## 6. Check-list sécurité

- [ ] Mot de passe administrateur long et unique.
- [ ] Accès depuis Internet uniquement en **HTTPS** (proxy inverse ou Tailscale), `PUBLIC_URL` renseigné.
- [ ] Sauvegardes régulières de `cinesync.db` (elle contient les jetons des services).
- [ ] Mises à jour : `git pull && docker compose up -d --build`, ou l'image publiée.

---
Les membres trouveront leur propre guide ici : [Membre de la famille](serveur-membre.md).
