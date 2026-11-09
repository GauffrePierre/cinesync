# Installer SynCiné

SynCiné tient dans **un seul conteneur Docker** (`ghcr.io/gauffrepierre/syncine`, PC et ARM) avec un seul dossier de données à sauvegarder. Il lui faut peu de ressources : 1 cœur, 512 Mo de mémoire (il en utilise environ 150), 1 Go de disque.

Choisis ton système :

- [Docker Compose](#docker-compose) : n'importe quelle machine Linux, mini-PC, Raspberry Pi, NAS avec Docker
- [Unraid](#unraid)
- [TrueNAS](#truenas)
- [Proxmox VE](#proxmox)
- [OpenMediaVault](#openmediavault)

Ensuite, quel que soit le système : [premier démarrage](#premier-démarrage), [HTTPS](#https), [mise à jour](#mise-à-jour).

Les réglages du conteneur sont les mêmes partout :

| Variable | Valeur | Rôle |
|---|---|---|
| `CINESYNC_MODE` | `server` ou `personal` | `server` : un administrateur et les comptes de la famille, avec connexion. `personal` : une seule personne, sans connexion (réseau de confiance uniquement) |
| `PUBLIC_URL` | ex. `https://syncine.exemple.fr` | Adresse HTTPS de SynCiné, si tu en as une (connexion Trakt, cookies sécurisés). Vide en réseau local |
| `TZ` | ex. `Europe/Paris` | Fuseau horaire |
| `PUID` / `PGID` | dépend du système | Propriétaire du dossier de données. SynCiné démarre en root, donne ce dossier à cet utilisateur, puis tourne sous son identité |

Le port de l'interface dans le conteneur est **8000** ; le dossier de données est **`/app/data`**.

## Docker Compose

Prérequis : Docker et son plugin Compose ([installation officielle](https://docs.docker.com/engine/install/)).

```bash
mkdir syncine && cd syncine
```

Crée `docker-compose.yml` :

```yaml
services:
  syncine:
    image: ghcr.io/gauffrepierre/syncine:latest
    container_name: syncine
    restart: unless-stopped
    ports:
      - "3000:8000"
    volumes:
      - ./data:/app/data
    environment:
      - CINESYNC_MODE=server
      - PUBLIC_URL=
      - TZ=Europe/Paris
      - PUID=1000      # résultat de la commande « id » : uid
      - PGID=1000      # gid
```

```bash
docker compose up -d
```

SynCiné est sur `http://<adresse-de-la-machine>:3000`. Passe au [premier démarrage](#premier-démarrage).

> Docker contourne les règles de pare-feu `ufw` / `firewalld` pour les ports publiés. Pour n'ouvrir SynCiné qu'à un proxy HTTPS installé sur la même machine, publie le port sur `127.0.0.1:3000:8000`.

## Unraid

**Avec le modèle** (en attendant que SynCiné soit dans la boutique *Apps*) :

1. Dans un terminal Unraid :
   ```bash
   wget -O /boot/config/plugins/dockerMan/templates-user/my-SynCine.xml \
     https://raw.githubusercontent.com/GauffrePierre/syncine/main/unraid/syncine.xml
   ```
2. **Docker → Add Container**, choisis **SynCiné** dans la liste *Template*.
3. Vérifie le port (3000 par défaut), le dossier de données (`/mnt/user/appdata/syncine`) et la version (`server` ou `personal`), puis **Apply**.

PUID/PGID valent 99/100 (`nobody:users`), l'usage sur Unraid. Pour le code d'installation : icône du conteneur → **Logs**.

Une installation avec Docker Compose (sans plugin) est décrite dans le [README](../../../README.md#sur-unraid).

## TrueNAS

TrueNAS Community Edition 24.10 ou plus récent (applications Docker).

1. **Un dataset pour les données** : **Datasets** → choisis le dataset parent (pas `ix-apps`) → **Add Dataset**, nom `syncine`, **Dataset Preset : Apps**, **Save**. Le préréglage *Apps* donne les droits au groupe `apps` (568).
2. **Installer** : **Apps → Discover Apps → ⋮ → Install via YAML**. Nom : `syncine`. Dans **Custom Config**, colle (en adaptant le chemin du dataset) :

   ```yaml
   services:
     syncine:
       image: ghcr.io/gauffrepierre/syncine:latest
       restart: unless-stopped
       ports:
         - "3000:8000"
       volumes:
         - /mnt/tank/syncine:/app/data
       environment:
         - CINESYNC_MODE=server
         - PUBLIC_URL=
         - TZ=Europe/Paris
         - PUID=568
         - PGID=568
   ```

3. **Save**. SynCiné est sur `http://<adresse-du-NAS>:3000` (change 3000 si le port est déjà pris). Le code d'installation : **Apps → Installed → syncine → Workloads → Logs**.

**Mise à jour** : **Apps → Installed → syncine → Update** quand TrueNAS en signale une ; sinon **Apps → Configuration → Manage Container Images → Pull Image** (`ghcr.io/gauffrepierre/syncine:latest`), puis redémarre l'application.

## Proxmox

Deux possibilités, à choisir selon tes habitudes :

- **un conteneur LXC Debian** avec Docker dedans : léger, c'est l'usage le plus courant en homelab ;
- **une machine virtuelle Debian** avec Docker : ce que recommande Proxmox pour les conteneurs d'application (migration à chaud, isolation complète). L'installation dans la VM suit alors la section [Docker Compose](#docker-compose).

### Conteneur LXC (Proxmox VE 8 ou 9)

Sur l'hôte Proxmox (**Shell** du nœud) :

```bash
pveam update
pveam available --section system | grep debian-13     # note le nom exact du modèle
pveam download local debian-13-standard_13.6-1_amd64.tar.zst
pct create 120 local:vztmpl/debian-13-standard_13.6-1_amd64.tar.zst \
  --hostname syncine --unprivileged 1 --features nesting=1,keyctl=1 \
  --cores 1 --memory 1024 --swap 512 --rootfs local-lvm:8 \
  --net0 name=eth0,bridge=vmbr0,ip=dhcp --onboot 1 --start 1
pct enter 120
```

Remplace `120` par un numéro libre, `local-lvm` par ton stockage et le nom du modèle par celui affiché. Par l'interface : **Create CT**, coche **Unprivileged container**, puis dans **Options → Features** coche **keyctl** et **Nesting**.

Dans le conteneur, installe Docker depuis son dépôt officiel :

```bash
apt update && apt install -y ca-certificates curl
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
cat > /etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/debian
Suites: $(. /etc/os-release && echo "$VERSION_CODENAME")
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF
apt update && apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
```

Puis suis la section [Docker Compose](#docker-compose) (dans le conteneur, `PUID=1000` et `PGID=1000` conviennent). L'adresse de SynCiné est celle du conteneur : `ip -4 addr show eth0`.

> Si Docker refuse de démarrer un conteneur avec une erreur `ip_unprivileged_port_start … permission denied`, mets Proxmox à jour (corrigé en 9.1). Sur une version plus ancienne, ajoute `lxc.sysctl.net.ipv4.ip_unprivileged_port_start=0` à `/etc/pve/lxc/120.conf` et redémarre le conteneur.

> Proxmox 9.1+ sait aussi lancer directement une image OCI comme conteneur LXC (**Pull from OCI registry**). C'est encore un *aperçu technologique*, et chaque mise à jour oblige à recréer le conteneur : on ne le conseille pas encore pour SynCiné.

## OpenMediaVault

OpenMediaVault 7 ou 8, avec le plugin **compose** d'omv-extras.

1. **omv-extras** (si ce n'est pas déjà fait), en SSH en root :
   ```bash
   wget -O - https://github.com/OpenMediaVault-Plugin-Developers/packages/raw/master/install | bash
   ```
2. **System → omv-extras** : active **Docker repo**, **Save**. Puis **System → Plugins** : installe **openmediavault-compose**.
3. **Dossiers partagés** (**Storage → Shared Folders**) : `appdata` (fichiers compose) et `data` (données des conteneurs), si tu ne les as pas déjà. Dans **Services → Compose → Settings**, choisis `appdata` pour **Compose Files** et `data` pour **Data**, puis **Save**.
4. **Un utilisateur pour les applications** : **Users → Users → + Create**, par exemple `appuser` (ne l'ajoute pas au groupe `docker`). Note son UID et son GID (bouton en haut à droite de la liste pour afficher ces colonnes).
5. **Services → Compose → Files → + → Add**, nom `syncine`, et colle :

   ```yaml
   services:
     syncine:
       image: ghcr.io/gauffrepierre/syncine:latest
       container_name: syncine
       restart: unless-stopped
       ports:
         - "3000:8000"
       volumes:
         - CHANGE_TO_COMPOSE_DATA_PATH/syncine:/app/data
       environment:
         - CINESYNC_MODE=server
         - PUBLIC_URL=
         - TZ=Europe/Paris
         - PUID=1000      # UID de appuser
         - PGID=100       # GID de son groupe (users = 100)
   ```

   `CHANGE_TO_COMPOSE_DATA_PATH` est remplacé par le plugin par le dossier **Data** choisi à l'étape 3.
6. **Save**, sélectionne le fichier puis **Up**. SynCiné est sur `http://<adresse-du-NAS>:3000` (le port 80 reste à l'interface d'OpenMediaVault). Le code d'installation : sélectionne le fichier → **Logs**.

**Mise à jour** : sélectionne le fichier → **Pull**, puis **Up**. Pour l'automatiser : **Services → Compose → Schedule**, tâche *Update*.

## Premier démarrage

- **Version serveur** : le premier écran crée le **compte administrateur** et demande un **code d'installation**, écrit dans les journaux du conteneur (`docker logs syncine 2>&1 | grep "code pour créer"`, ou la vue *Logs* de ton système).
- **Version personnelle** : l'application s'ouvre directement. Protège-la par un mot de passe si elle est accessible hors de chez toi.

Un assistant te guide ensuite : langue, pays, clé TMDB, plateformes, cinémas, serveur multimédia (Plex, Jellyfin, Emby), notifications. La suite est dans les guides [administrateur](serveur-admin.md) et [version personnelle](version-personnelle.md).

## HTTPS

Pour installer SynCiné comme une application sur téléphone, recevoir les notifications push et l'utiliser hors de chez toi, il faut une adresse **HTTPS** : Tailscale (sans ouvrir de port) ou un nom de domaine derrière un proxy inverse (Caddy, Nginx Proxy Manager, Traefik…). Les deux sont décrits dans le [README](../../../README.md#accès-https-et-application-mobile). Renseigne ensuite cette adresse dans `PUBLIC_URL`.

## Mise à jour

La base est migrée automatiquement au démarrage, et SynCiné en fait une sauvegarde chaque jour (dossier `backups/` des données).

| Système | Mise à jour |
|---|---|
| Docker Compose, Proxmox | `docker compose pull && docker compose up -d` |
| Unraid | **Docker → Check for Updates**, puis **Apply Update** |
| TrueNAS | **Apps → Installed → syncine → Update** |
| OpenMediaVault | **Services → Compose → Files** → fichier → **Pull** puis **Up** |
