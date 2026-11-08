# Sécurité / Security

**Français** — Si tu trouves une faille de sécurité dans SynCiné, ne la publie pas dans une issue :
signale-la de façon privée via l'onglet **Security → Report a vulnerability** du dépôt GitHub.
Merci d'indiquer la version concernée, les étapes pour reproduire et l'impact possible.

**English** — If you find a security issue in SynCiné, please do not open a public issue:
report it privately through the repository's **Security → Report a vulnerability** tab on GitHub.
Please include the affected version, steps to reproduce and the possible impact.

## Bonnes pratiques de déploiement / Deployment notes

- Version `server` : accès par connexion (mots de passe hachés scrypt, cookies HttpOnly / SameSite, essais limités).
- Version `personal` : **aucune connexion** — à garder sur un réseau de confiance (réseau local, Tailscale), jamais exposée directement sur Internet.
- Sur Internet, place SynCiné derrière un proxy HTTPS et renseigne `PUBLIC_URL` en `https://` ; avec un domaine dédié, active `HSTS_SECONDS`.
- La base `cinesync.db` contient les jetons des services connectés : sauvegarde-la comme un secret.
