# Installing SynCiné

SynCiné runs in **a single Docker container** (`ghcr.io/gauffrepierre/syncine`, PC and ARM) with a single data folder to back up. It needs few resources: 1 core, 512 MB of memory (it uses about 150), 1 GB of disk.

Pick your system:

- [Docker Compose](#docker-compose): any Linux machine, mini PC, Raspberry Pi, NAS with Docker
- [Unraid](#unraid)
- [TrueNAS](#truenas)
- [Proxmox VE](#proxmox)
- [OpenMediaVault](#openmediavault)

Then, whatever the system: [first start](#first-start), [HTTPS](#https), [updates](#updates).

The container settings are the same everywhere:

| Variable | Value | Purpose |
|---|---|---|
| `CINESYNC_MODE` | `server` or `personal` | `server`: an administrator and family accounts, with sign-in. `personal`: one person, no sign-in (trusted networks only) |
| `PUBLIC_URL` | e.g. `https://syncine.example.org` | SynCiné's HTTPS address, if you have one (Trakt sign-in, secure cookies). Empty on a local network |
| `TZ` | e.g. `Europe/London` | Time zone |
| `PUID` / `PGID` | depends on the system | Owner of the data folder. SynCiné starts as root, hands this folder to that user, then runs as that user |

The interface port inside the container is **8000**; the data folder is **`/app/data`**.

## Docker Compose

Requirements: Docker and its Compose plugin ([official install](https://docs.docker.com/engine/install/)).

```bash
mkdir syncine && cd syncine
```

Create `docker-compose.yml`:

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
      - TZ=Europe/London
      - PUID=1000      # output of the "id" command: uid
      - PGID=1000      # gid
```

```bash
docker compose up -d
```

SynCiné is at `http://<machine-address>:3000`. Go to [first start](#first-start).

> Docker bypasses `ufw` / `firewalld` rules for published ports. To expose SynCiné only to an HTTPS proxy on the same machine, publish the port as `127.0.0.1:3000:8000`.

## Unraid

**With the template** (until SynCiné is in the *Apps* store):

1. In an Unraid terminal:
   ```bash
   wget -O /boot/config/plugins/dockerMan/templates-user/my-SynCine.xml \
     https://raw.githubusercontent.com/GauffrePierre/syncine/main/unraid/syncine.xml
   ```
2. **Docker → Add Container**, pick **SynCiné** from the *Template* list.
3. Check the port (3000 by default), the data folder (`/mnt/user/appdata/syncine`) and the edition (`server` or `personal`), then **Apply**.

PUID/PGID are 99/100 (`nobody:users`), the Unraid convention. For the setup code: container icon → **Logs**.

An install with Docker Compose (no plugin) is described in the [README](../../../README.en.md#on-unraid).

## TrueNAS

TrueNAS Community Edition 24.10 or later (Docker apps).

1. **A dataset for the data**: **Datasets** → pick the parent dataset (not `ix-apps`) → **Add Dataset**, name `syncine`, **Dataset Preset: Apps**, **Save**. The *Apps* preset grants access to the `apps` group (568).
2. **Install**: **Apps → Discover Apps → ⋮ → Install via YAML**. Name: `syncine`. In **Custom Config**, paste (adjusting the dataset path):

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
         - TZ=Europe/London
         - PUID=568
         - PGID=568
   ```

3. **Save**. SynCiné is at `http://<nas-address>:3000` (change 3000 if the port is taken). The setup code: **Apps → Installed → syncine → Workloads → Logs**.

**Updates**: **Apps → Installed → syncine → Update** when TrueNAS reports one; otherwise **Apps → Configuration → Manage Container Images → Pull Image** (`ghcr.io/gauffrepierre/syncine:latest`), then restart the app.

## Proxmox

Two options, depending on your habits:

- **a Debian LXC container** with Docker inside: lightweight, the most common homelab setup;
- **a Debian virtual machine** with Docker: what Proxmox recommends for application containers (live migration, full isolation). Inside the VM, follow the [Docker Compose](#docker-compose) section.

### LXC container (Proxmox VE 8 or 9)

On the Proxmox host (the node's **Shell**):

```bash
pveam update
pveam available --section system | grep debian-13     # note the exact template name
pveam download local debian-13-standard_13.6-1_amd64.tar.zst
pct create 120 local:vztmpl/debian-13-standard_13.6-1_amd64.tar.zst \
  --hostname syncine --unprivileged 1 --features nesting=1,keyctl=1 \
  --cores 1 --memory 1024 --swap 512 --rootfs local-lvm:8 \
  --net0 name=eth0,bridge=vmbr0,ip=dhcp --onboot 1 --start 1
pct enter 120
```

Replace `120` with a free ID, `local-lvm` with your storage and the template name with the one listed. In the web UI: **Create CT**, tick **Unprivileged container**, then in **Options → Features** tick **keyctl** and **Nesting**.

Inside the container, install Docker from its official repository:

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

Then follow the [Docker Compose](#docker-compose) section (inside the container, `PUID=1000` and `PGID=1000` are fine). SynCiné's address is the container's: `ip -4 addr show eth0`.

> If Docker refuses to start a container with an `ip_unprivileged_port_start … permission denied` error, update Proxmox (fixed in 9.1). On an older version, add `lxc.sysctl.net.ipv4.ip_unprivileged_port_start=0` to `/etc/pve/lxc/120.conf` and restart the container.

> Proxmox 9.1+ can also run an OCI image directly as an LXC container (**Pull from OCI registry**). It is still a *technology preview*, and every update means recreating the container, so it isn't recommended for SynCiné yet.

## OpenMediaVault

OpenMediaVault 7 or 8, with the **compose** plugin from omv-extras.

1. **omv-extras** (if not already installed), over SSH as root:
   ```bash
   wget -O - https://github.com/OpenMediaVault-Plugin-Developers/packages/raw/master/install | bash
   ```
2. **System → omv-extras**: enable **Docker repo**, **Save**. Then **System → Plugins**: install **openmediavault-compose**.
3. **Shared folders** (**Storage → Shared Folders**): `appdata` (compose files) and `data` (container data), if you don't have them yet. In **Services → Compose → Settings**, pick `appdata` for **Compose Files** and `data` for **Data**, then **Save**.
4. **A user for apps**: **Users → Users → + Create**, for example `appuser` (don't add it to the `docker` group). Note its UID and GID (button at the top right of the list to show those columns).
5. **Services → Compose → Files → + → Add**, name `syncine`, and paste:

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
         - TZ=Europe/London
         - PUID=1000      # appuser's UID
         - PGID=100       # its group's GID (users = 100)
   ```

   The plugin replaces `CHANGE_TO_COMPOSE_DATA_PATH` with the **Data** folder chosen in step 3.
6. **Save**, select the file, then **Up**. SynCiné is at `http://<nas-address>:3000` (port 80 stays with the OpenMediaVault interface). The setup code: select the file → **Logs**.

**Updates**: select the file → **Pull**, then **Up**. To automate it: **Services → Compose → Schedule**, *Update* task.

## First start

- **Server edition**: the first screen creates the **administrator account** and asks for a **setup code**, written to the container logs (`docker logs syncine 2>&1 | grep "code pour créer"`, or your system's *Logs* view).
- **Personal edition**: the app opens directly. Protect it with a password if it can be reached from outside your home.

An assistant then walks you through: language, country, TMDB key, streaming services, cinemas, media server (Plex, Jellyfin, Emby), notifications. Next steps are in the [administrator](server-admin.md) and [personal edition](personal-edition.md) guides.

## HTTPS

To install SynCiné as an app on your phone, get push notifications and use it away from home, you need an **HTTPS** address: Tailscale (no open port) or a domain name behind a reverse proxy (Caddy, Nginx Proxy Manager, Traefik…). Both are described in the [README](../../../README.en.md#https-access-and-mobile-app). Then put that address in `PUBLIC_URL`.

## Updates

The database is migrated automatically at startup, and SynCiné backs it up every day (`backups/` in the data folder).

| System | Update |
|---|---|
| Docker Compose, Proxmox | `docker compose pull && docker compose up -d` |
| Unraid | **Docker → Check for Updates**, then **Apply Update** |
| TrueNAS | **Apps → Installed → syncine → Update** |
| OpenMediaVault | **Services → Compose → Files** → file → **Pull** then **Up** |
