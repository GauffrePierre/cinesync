# Démarrer en tant que membre de la famille

> À ta première connexion, un **assistant** te guide en quelques écrans : langue et pays, plateformes, cinémas, comptes et notifications. Tu peux le relancer plus tard (Profil → Apparence → Revoir l’assistant de démarrage).

Quelqu'un t'a ouvert un compte sur son SynCiné. Tu as ta propre watchlist, tes notes, tes services et tes réglages : personne d'autre ne les voit. Compte 5 minutes.

Ouvre l'adresse que l'on t'a donnée (elle commence par `https://`), puis suis le cas qui te concerne.

## Avec un compte Plex

L'administrateur a autorisé ton compte Plex.

1. Sur l'écran **Connexion**, choisis **Se connecter avec Plex**.
2. Un code de 4 caractères s'affiche : va sur [plex.tv/link](https://plex.tv/link), connecte-toi avec ton compte Plex habituel et saisis le code. (Ou utilise « ouvrir la fenêtre de connexion Plex ».)
3. Reviens sur SynCiné : tu es connecté. Tes vus et ta progression Plex sont les tiens.

Si on t'a aussi donné un mot de passe provisoire, ou si tu veux pouvoir te connecter sans Plex : **Profil → Mon compte → Créer un mot de passe**.

## Avec un compte Jellyfin ou Emby

L'administrateur a autorisé ton compte Jellyfin (ou Emby).

1. Sur l'écran **Connexion**, choisis **Se connecter avec Jellyfin** (ou Emby).
2. Si un code à 6 chiffres s'affiche (**Quick Connect**) : dans ton application Jellyfin ou sur le site, ouvre ton profil → **Quick Connect** et saisis ce code. SynCiné te connecte dès que tu l'as validé, sans ton mot de passe Jellyfin. Sinon, saisis ton identifiant et ton mot de passe Jellyfin : ils sont vérifiés par le serveur, SynCiné ne les garde pas.
3. Tes titres vus sur Jellyfin sont les tiens, et « Lire » ouvre le titre sur Jellyfin.

Tu as déjà un compte SynCiné ? Relie ton compte Jellyfin dans **Profil → Connexions → + → Jellyfin / Emby → Relier mon compte** (ton mot de passe SynCiné est demandé ; avec Quick Connect, tu valides ensuite un code dans Jellyfin). Pour pouvoir ensuite te connecter avec lui, demande-le à l'administrateur.

## Sans compte Plex

L'administrateur t'a donné un **identifiant** et un **mot de passe provisoire**. Tu as accès à tout SynCiné (découverte, cinémas, streaming, watchlist, Trakt, Letterboxd…), sauf à ce qui concerne le serveur multimédia (Plex, Jellyfin ou Emby) : sa bibliothèque et les demandes d'ajout.

1. Sur l'écran **Connexion**, saisis-les et choisis **Se connecter**.
2. Choisis ton propre mot de passe (8 caractères minimum) : c'est demandé à la première connexion.

## Ensuite, pour tout le monde

Dans **Profil** :

1. **Région & Langue** : ton pays, la langue des contenus et la langue de l'interface.
2. **Plateformes** : coche tes abonnements (badges, filtres, « Regarder sur… », notifications).
3. **Cinémas** : tes salles habituelles.
4. **Connexions → +** : relie **ton** compte Trakt (**Se connecter avec Trakt**, code sur trakt.tv/activate) et/ou ton Letterboxd, si tu en as.
5. **Synchronisation** : **Synchroniser maintenant** rassemble ta watchlist, tes vus et tes notes.
6. **Notifications** : choisis ce que tu veux voir sous la cloche.
7. **Préférences → Partage avec l'administrateur** (facultatif) : l'administrateur voit les titres de ta watchlist que tu ne peux regarder nulle part, pour savoir quoi ajouter à la bibliothèque. Rien d'autre n'est partagé, et tu peux l'arrêter à tout moment.
8. **Mon compte → Double authentification** (conseillé) : scanne le QR code avec une application d'authentification (Aegis, Google Authenticator, Bitwarden…) et garde les codes de secours. Téléphone perdu ? Utilise un code de secours, ou demande à l'administrateur de la réinitialiser.

### Demander un film ou une série (comptes Plex, Jellyfin ou Emby)
Les demandes servent à ajouter un titre au serveur : elles sont proposées aux comptes reliés au serveur multimédia. Sur la fiche d'un titre absent de la bibliothèque : **Demander l'ajout**. Selon ce qu'a réglé l'administrateur, la demande part directement, ou il la reçoit et la traite ; tu es prévenu dans les notifications. Suis tes demandes dans **Profil → Mes demandes**.

### Installer l'appli sur ton téléphone
- **iPhone / iPad** : Safari → **Partager → Sur l'écran d'accueil**. « Lire sur Plex » te proposera d'ouvrir l'app Plex.
- **Android** : Chrome propose l'installation ; les liens « Regarder sur… » ouvrent directement les applis installées.

---
Un problème de connexion ? Demande à l'administrateur de vérifier ton compte (Profil → Admin → Comptes).
